"""Docker container management for media stack services.

Ensures safe container operations:
- Never touches unmanaged containers (missing io.unifierr.managed=true).
- Refuses to overwrite existing containers on install.
- Performs atomic updates with automated rollback if the new container fails.
- Lazy connection with plain-English diagnostics for Docker socket issues.
"""
from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.adapters.base import ServiceKind
from app.core.errors import UnifierrError
from app.deploy.catalog import AppSpec


class ContainerInfo(BaseModel):
    id: str
    name: str
    image: str
    status: str  # running|exited|...
    health: str | None
    ports: dict[int, int | None]  # container port -> host port
    networks: list[str]
    mounts: list[dict]  # [{source, destination}]
    labels: dict[str, str]


class DockerManager:
    def __init__(self, docker_host: str | None = None, *, client: Any = None):
        self.docker_host = docker_host
        self._client = client
        self._error: str | None = None

    @property
    def client(self) -> Any:
        if self._client is None:
            self._ensure_client()
        return self._client

    def _ensure_client(self) -> None:
        try:
            import docker
        except ImportError as exc:
            self._error = "The 'docker' Python library is not installed."
            raise UnifierrError("Docker library missing", explanation=self._error) from exc

        try:
            if self.docker_host:
                self._client = docker.DockerClient(base_url=self.docker_host)
            else:
                self._client = docker.from_env()
            self._client.ping()
            self._error = None
        except Exception as exc:  # noqa: BLE001
            self._client = None
            self._error = self._format_error(exc)
            raise UnifierrError(
                "Cannot connect to Docker daemon",
                explanation=self._error,
                fix="Verify Docker is running and the socket path is correct.",
            ) from exc

    def _format_error(self, exc: Exception) -> str:
        msg = str(exc)
        host_desc = self.docker_host or "default socket"
        msg_lower = msg.lower()

        if (
            isinstance(exc, FileNotFoundError)
            or "no such file or directory" in msg_lower
            or "filenotfound" in msg_lower
            or "pipe" in msg_lower
            or "af_unix" in msg_lower
            or "unix" in host_desc.lower()
        ):
            return (
                f"Docker socket is not available at '{host_desc}'. "
                "If running Unifierr inside Docker, ensure the Docker socket is mounted in your compose file: "
                "'- /var/run/docker.sock:/var/run/docker.sock'."
            )
        if isinstance(exc, PermissionError) or "permission denied" in msg_lower or "403" in msg_lower:
            return (
                f"Permission denied connecting to Docker socket at '{host_desc}'. "
                "Ensure Unifierr has permission to read and write to /var/run/docker.sock "
                "(e.g. running as root or a member of the docker group)."
            )
        if "connection refused" in msg_lower or "connect error" in msg_lower:
            return (
                f"Cannot connect to Docker daemon at '{host_desc}'. "
                "Make sure Docker is installed and the Docker service is actively running."
            )
        return f"Failed to connect to Docker daemon at '{host_desc}': {exc}"

    def available(self) -> bool:
        """Check whether the Docker daemon is accessible."""
        try:
            c = self.client
            if hasattr(c, "ping"):
                c.ping()
            return True
        except Exception as exc:  # noqa: BLE001
            self._error = self._format_error(exc)
            return False

    def error(self) -> str | None:
        """Return a plain-English explanation if Docker is unavailable."""
        if self.available():
            return None
        return self._error or "Docker daemon is not available."

    def info(self) -> dict[str, Any]:
        """Return daemon system info if available."""
        if not self.available():
            return {}
        try:
            return self.client.info()
        except Exception:  # noqa: BLE001
            return {}

    def version(self) -> str | None:
        """Return daemon version string if available."""
        if not self.available():
            return None
        try:
            v = self.client.version()
            if isinstance(v, dict):
                return v.get("Version")
            return str(v)
        except Exception:  # noqa: BLE001
            return None

    def list_containers(self, all: bool = True) -> list[ContainerInfo]:
        """List containers on the Docker host."""
        if not self.available():
            return []
        try:
            containers = self.client.containers.list(all=all)
            return [self._to_container_info(c) for c in containers]
        except Exception as exc:  # noqa: BLE001
            raise UnifierrError(
                f"Failed to list containers: {exc}",
                explanation="Docker daemon returned an error while listing containers.",
            ) from exc

    def _to_container_info(self, c: Any) -> ContainerInfo:
        c_id = str(getattr(c, "id", "") or "")
        raw_name = str(getattr(c, "name", "") or "")
        c_name = raw_name.lstrip("/")

        attrs = getattr(c, "attrs", {})
        if not isinstance(attrs, dict):
            attrs = {}
        config = attrs.get("Config", {})
        if not isinstance(config, dict):
            config = {}
        state = attrs.get("State", {})
        if not isinstance(state, dict):
            state = {}
        network_settings = attrs.get("NetworkSettings", {})
        if not isinstance(network_settings, dict):
            network_settings = {}

        # Resolve image string
        image_name = ""
        if isinstance(config.get("Image"), str) and config["Image"]:
            image_name = config["Image"]
        elif hasattr(c, "image"):
            img = c.image
            if hasattr(img, "tags") and isinstance(img.tags, list) and img.tags:
                image_name = str(img.tags[0])
            elif hasattr(img, "id") and isinstance(img.id, str):
                image_name = img.id
            elif isinstance(img, str):
                image_name = img
            else:
                image_name = str(img)
        if not image_name and "Image" in config:
            image_name = str(config["Image"])

        # Status
        raw_status = getattr(c, "status", None)
        if isinstance(raw_status, str):
            status = raw_status
        elif isinstance(state.get("Status"), str):
            status = state["Status"]
        else:
            status = "unknown"

        health = None
        if isinstance(state.get("Health"), dict) and isinstance(state["Health"].get("Status"), str):
            health = state["Health"]["Status"]

        # Parse ports
        ports_dict: dict[int, int | None] = {}
        raw_ports = network_settings.get("Ports") or getattr(c, "ports", {}) or {}
        if isinstance(raw_ports, dict):
            for port_key, bindings in raw_ports.items():
                if not port_key:
                    continue
                port_part = str(port_key).split("/")[0]
                try:
                    p_int = int(port_part)
                except ValueError:
                    continue

                host_p: int | None = None
                if bindings and isinstance(bindings, list) and len(bindings) > 0:
                    b = bindings[0]
                    if isinstance(b, dict) and "HostPort" in b:
                        with contextlib.suppress(ValueError, TypeError):
                            host_p = int(b["HostPort"])
                elif isinstance(bindings, int):
                    host_p = bindings
                ports_dict[p_int] = host_p

        # Networks
        networks_dict = network_settings.get("Networks", {})
        networks = list(networks_dict.keys()) if isinstance(networks_dict, dict) else []

        # Mounts
        mounts_list = attrs.get("Mounts", [])
        mounts = []
        if isinstance(mounts_list, list):
            for m in mounts_list:
                if isinstance(m, dict):
                    mounts.append({
                        "source": str(m.get("Source", "")),
                        "destination": str(m.get("Destination", "")),
                    })

        # Labels
        raw_labels = getattr(c, "labels", None)
        if not isinstance(raw_labels, dict):
            raw_labels = config.get("Labels", {})
        labels = {str(k): str(v) for k, v in raw_labels.items()} if isinstance(raw_labels, dict) else {}

        return ContainerInfo(
            id=c_id,
            name=c_name,
            image=image_name,
            status=status,
            health=health,
            ports=ports_dict,
            networks=networks,
            mounts=mounts,
            labels=labels,
        )

    def ensure_network(self, name: str = "unifierr") -> None:
        """Ensure the specified bridge network exists."""
        if not self.available():
            raise UnifierrError("Docker is not available", explanation=self.error())
        try:
            self.client.networks.get(name)
        except Exception:  # noqa: BLE001
            try:
                self.client.networks.create(name, driver="bridge")
            except Exception as exc:  # noqa: BLE001
                try:
                    self.client.networks.get(name)
                except Exception:  # noqa: BLE001
                    raise UnifierrError(
                        f"Could not create Docker network '{name}': {exc}",
                        explanation="Failed to create the shared network for Unifierr apps.",
                        fix="Check Docker daemon permissions and network drivers.",
                    ) from exc

    def connect_network(self, container: str, network: str = "unifierr") -> None:
        """Connect a container to a network non-destructively."""
        if not self.available():
            raise UnifierrError("Docker is not available", explanation=self.error())
        try:
            net = self.client.networks.get(network)
            net.connect(container)
        except Exception as exc:  # noqa: BLE001
            err_str = str(exc).lower()
            if "already exists" in err_str or "already in network" in err_str:
                return
            raise UnifierrError(
                f"Failed to connect container '{container}' to network '{network}': {exc}",
                explanation="Could not connect the container to the shared network.",
            ) from exc

    def install(
        self,
        spec: AppSpec,
        *,
        root: str,
        puid: int,
        pgid: int,
        tz: str,
        host_port: int | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> ContainerInfo:
        """Pull an image and create a managed container with standard labels and mounts.

        Refuses if a container with the target name already exists.
        """
        if not self.available():
            raise UnifierrError("Docker is not available", explanation=self.error())

        # 1. Refuse if container already exists
        try:
            existing = self.client.containers.get(spec.container_name)
            if existing:
                raise UnifierrError(
                    f"Container '{spec.container_name}' already exists",
                    explanation=(
                        f"A container named '{spec.container_name}' already exists on this Docker host. "
                        "Unifierr will never overwrite or modify existing containers."
                    ),
                    fix=f"Stop or rename '{spec.container_name}', or connect it in Settings -> Apps.",
                )
        except UnifierrError:
            raise
        except Exception:  # noqa: BLE001, S110
            pass

        # 2. Pull image with stream progress
        if progress:
            progress(f"Pulling image {spec.image}...")
        try:
            for line in self.client.api.pull(spec.image, stream=True, decode=True):
                if progress and isinstance(line, dict):
                    detail = line.get("progressDetail", {})
                    current = detail.get("current")
                    total = detail.get("total")
                    status = line.get("status", "")
                    if current and total:
                        pct = int(current / total * 100)
                        progress(f"Downloading {spec.container_name}: {pct}%")
                    elif status:
                        progress(f"{spec.container_name}: {status}")
        except Exception as exc:  # noqa: BLE001
            raise UnifierrError(
                f"Failed to pull image '{spec.image}'",
                explanation=f"Docker failed to download '{spec.image}': {exc}",
                fix="Check your internet connection and Docker registry access.",
            ) from exc

        # 3. Ensure network
        self.ensure_network("unifierr")

        # 4. Volumes
        appdata_path = f"{root}/appdata"
        volumes: dict[str, dict[str, str]] = {}
        for host_tmpl, container_path in spec.volumes.items():
            host_p = host_tmpl.format(root=root, appdata=appdata_path)
            volumes[host_p] = {"bind": container_path, "mode": "rw"}

        # 5. Env
        env: dict[str, str] = {}
        for k, v in spec.env.items():
            env[k] = v.format(puid=puid, pgid=pgid, tz=tz)

        # 6. Ports
        port_to_bind = host_port or spec.default_host_port
        ports: dict[str, Any] = {f"{spec.internal_port}/tcp": port_to_bind}
        if spec.kind == ServiceKind.qbittorrent:
            ports["6881/tcp"] = 6881
            ports["6881/udp"] = 6881

        # 7. Labels
        labels = {
            "io.unifierr.managed": "true",
            "io.unifierr.kind": spec.kind.value,
        }

        # 8. Create and start. If starting fails, remove the container we just created so a
        # retry is possible (it is ours, it never held user data).
        container = None
        try:
            container = self.client.containers.create(
                image=spec.image,
                name=spec.container_name,
                environment=env,
                volumes=volumes,
                ports=ports,
                restart_policy={"Name": "unless-stopped"},
                labels=labels,
                network="unifierr",
            )
            container.start()
        except Exception as exc:  # noqa: BLE001
            if container is not None:
                with contextlib.suppress(Exception):
                    container.remove(force=True)
            text = str(exc).lower()
            if "port is already allocated" in text or "address already in use" in text:
                raise UnifierrError(
                    f"Port {port_to_bind} is already in use",
                    explanation=f"Another program on this computer already uses port {port_to_bind}, "
                                f"so {spec.display_name} cannot use it.",
                    fix=f"If you already run {spec.display_name}, connect it instead of installing it. "
                        "Otherwise stop the program using that port and press Retry.",
                ) from exc
            raise UnifierrError(
                f"Failed to start container '{spec.container_name}'",
                explanation=f"Docker failed to start '{spec.container_name}': {exc}",
                fix="Check Docker logs or inspect port conflicts.",
            ) from exc

        if progress:
            progress(f"{spec.display_name} installed and started.")
        return self._to_container_info(container)

    @staticmethod
    def _assert_managed(c: Any, name: str) -> None:
        """Second safety net: never start/stop/restart a container Unifierr did not create."""
        labels = getattr(c, "labels", None) or (getattr(c, "attrs", {}) or {}).get("Config", {}).get("Labels") or {}
        if labels.get("io.unifierr.managed") != "true":
            raise UnifierrError(f"Container '{name}' is not managed by Unifierr",
                                explanation="Unifierr only starts, stops or restarts containers it installed.")

    def start(self, name: str) -> None:
        if not self.available():
            raise UnifierrError("Docker is not available", explanation=self.error())
        try:
            c = self.client.containers.get(name)
            self._assert_managed(c, name)
            c.start()
        except UnifierrError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise UnifierrError(f"Failed to start container '{name}': {exc}") from exc

    def stop(self, name: str) -> None:
        if not self.available():
            raise UnifierrError("Docker is not available", explanation=self.error())
        try:
            c = self.client.containers.get(name)
            self._assert_managed(c, name)
            c.stop()
        except UnifierrError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise UnifierrError(f"Failed to stop container '{name}': {exc}") from exc

    def restart(self, name: str) -> None:
        if not self.available():
            raise UnifierrError("Docker is not available", explanation=self.error())
        try:
            c = self.client.containers.get(name)
            self._assert_managed(c, name)
            c.restart()
        except UnifierrError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise UnifierrError(f"Failed to restart container '{name}': {exc}") from exc

    def logs(self, name: str, tail: int = 200) -> str:
        if not self.available():
            raise UnifierrError("Docker is not available", explanation=self.error())
        try:
            c = self.client.containers.get(name)
            raw = c.logs(tail=tail)
            if isinstance(raw, bytes):
                return raw.decode("utf-8", errors="replace")
            return str(raw)
        except Exception as exc:  # noqa: BLE001
            raise UnifierrError(f"Failed to fetch logs for container '{name}': {exc}") from exc

    def self_container(self) -> ContainerInfo | None:
        """Find Unifierr's own container by hostname or cgroup."""
        if not self.available():
            return None

        # 1. Hostname environment variable
        hostname = os.environ.get("HOSTNAME")
        if hostname:
            with contextlib.suppress(Exception):  # noqa: BLE001
                c = self.client.containers.get(hostname)
                return self._to_container_info(c)

        # 2. /etc/hostname file
        try:
            h_path = Path("/etc/hostname")
            if h_path.is_file():
                h = h_path.read_text(encoding="utf-8").strip()
                if h:
                    with contextlib.suppress(Exception):  # noqa: BLE001
                        c = self.client.containers.get(h)
                        return self._to_container_info(c)
        except OSError:
            pass

        # 3. cgroups
        for proc in ("/proc/self/cgroup", "/proc/1/cpuset"):
            try:
                p = Path(proc)
                if p.is_file():
                    content = p.read_text(encoding="utf-8")
                    m = re.search(r"([0-9a-f]{64})", content)
                    if m:
                        with contextlib.suppress(Exception):  # noqa: BLE001
                            c = self.client.containers.get(m.group(1))
                            return self._to_container_info(c)
            except OSError:
                pass
        return None

    def update(
        self,
        name: str,
        progress: Callable[[str], None] | None = None,
    ) -> ContainerInfo:
        """Pull newer image and recreate a managed container preserving all configurations.

        Only allowed on managed containers.
        Renames existing container to <name>-old until the new container is running,
        then removes the old one. If starting the new container fails, rolls back.
        """
        if not self.available():
            raise UnifierrError("Docker is not available", explanation=self.error())

        # 1. Verify container exists and is managed
        try:
            c = self.client.containers.get(name)
        except Exception as exc:  # noqa: BLE001
            raise UnifierrError(f"Container '{name}' not found: {exc}") from exc

        labels = getattr(c, "labels", None)
        if labels is None:
            labels = c.attrs.get("Config", {}).get("Labels", {}) or {}

        if labels.get("io.unifierr.managed") != "true":
            raise UnifierrError(
                f"Container '{name}' is not managed by Unifierr",
                explanation="To avoid breaking your setup, Unifierr only updates containers it installed.",
                fix="Update this container through your host package manager or Docker compose.",
            )

        # 2. Extract configuration
        attrs = getattr(c, "attrs", {}) or {}
        config = attrs.get("Config", {}) or {}
        host_config = attrs.get("HostConfig", {}) or {}
        network_settings = attrs.get("NetworkSettings", {}) or {}

        image_name = config.get("Image", "")
        env = config.get("Env", [])
        binds = host_config.get("Binds", [])
        port_bindings = host_config.get("PortBindings", {})
        restart_policy = host_config.get("RestartPolicy") or {"Name": "unless-stopped"}

        networks = list(network_settings.get("Networks", {}).keys())
        primary_net = networks[0] if networks else "unifierr"
        extra_nets = networks[1:]

        # 3. Pull newer image
        if progress:
            progress(f"Checking for updates for {name} ({image_name})...")
        try:
            for line in self.client.api.pull(image_name, stream=True, decode=True):
                if progress and isinstance(line, dict):
                    detail = line.get("progressDetail", {})
                    current = detail.get("current")
                    total = detail.get("total")
                    status = line.get("status", "")
                    if current and total:
                        pct = int(current / total * 100)
                        progress(f"Downloading {name}: {pct}%")
                    elif status:
                        progress(f"{name}: {status}")
        except Exception as exc:  # noqa: BLE001
            raise UnifierrError(
                f"Failed to pull latest image for '{name}'",
                explanation=f"Docker failed to download '{image_name}': {exc}",
                fix="Check your network connection and registry availability.",
            ) from exc

        # 4. Rename old container to <name>-old
        old_name = f"{name}-old"
        with contextlib.suppress(Exception):  # noqa: BLE001
            stale_old = self.client.containers.get(old_name)
            stale_old.remove(force=True)

        c.stop()
        c.rename(old_name)

        # 5. Create and start new container, rolling back on failure
        new_c = None
        try:
            if progress:
                progress(f"Recreating container {name}...")
            new_c = self.client.containers.create(
                image=image_name,
                name=name,
                environment=env,
                volumes=binds,
                ports=port_bindings,
                restart_policy=restart_policy,
                labels=labels,
                network=primary_net,
            )
            for extra_net in extra_nets:
                with contextlib.suppress(Exception):  # noqa: BLE001
                    self.client.networks.get(extra_net).connect(new_c)
            new_c.start()
        except Exception as exc:  # noqa: BLE001
            # ROLLBACK
            if progress:
                progress(f"Update failed ({exc}), rolling back to previous container...")
            if new_c is not None:
                with contextlib.suppress(Exception):  # noqa: BLE001
                    new_c.remove(force=True)
            try:
                c.rename(name)
                c.start()
            except Exception as rollback_exc:  # noqa: BLE001
                raise UnifierrError(
                    f"Update failed for '{name}' and rollback failed: {rollback_exc}",
                    explanation=(
                        f"Failed to start new container ({exc}), and failed to restore "
                        f"old container ({rollback_exc})."
                    ),
                    fix=f"Manually restore the container using 'docker start {old_name}'.",
                ) from exc
            raise UnifierrError(
                f"Failed to update '{name}', rolled back successfully",
                explanation=f"Starting the updated container failed: {exc}. The previous version was restored.",
                fix="Check Docker logs for errors.",
            ) from exc

        # 6. Success: remove old container
        with contextlib.suppress(Exception):  # noqa: BLE001
            c.remove(force=True)

        if progress:
            progress(f"{name} updated successfully.")
        return self._to_container_info(new_c)
