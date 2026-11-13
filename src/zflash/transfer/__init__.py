# Copyright (c) 2025 eInfochips
# SPDX-License-Identifier: Apache-2.0

"""Transfer backends: ways to enumerate and fetch artifacts from the server."""

from typing import List

from zflash.artifact import Artifact
from zflash.config import Config


def get_backend(cfg: Config):
    if cfg.server.transport == "http":
        from zflash.transfer.http import HttpBackend

        return HttpBackend(cfg)
    if cfg.server.transport == "ssh":
        from zflash.transfer.ssh import SshBackend

        return SshBackend(cfg)
    raise ValueError(f"unknown transport '{cfg.server.transport}' (ssh|http)")


def list_artifacts(cfg: Config) -> List[Artifact]:
    return get_backend(cfg).list_artifacts()


def pull(cfg: Config, artifact: Artifact, dest_dir) -> object:
    return get_backend(cfg).pull(artifact, dest_dir)
