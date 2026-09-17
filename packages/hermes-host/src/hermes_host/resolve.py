"""Select and order enabled plugins. Fail closed on cycles and ambiguity."""

from __future__ import annotations

from dataclasses import dataclass, field

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from hermes_host.config import HostConfig
from hermes_host.errors import CompositionError, PluginError
from hermes_host.metadata import PluginMetadata


@dataclass
class Composition:
    selected: tuple[PluginMetadata, ...]
    discovered: tuple[PluginMetadata, ...]
    skipped: dict[str, str] = field(default_factory=dict)
    service_owners: dict[str, tuple[str, ...]] = field(default_factory=dict)


def resolve_composition(
    discovered: list[PluginMetadata],
    config: HostConfig,
) -> Composition:
    """Choose the enabled set, validate deps/uniqueness, and return a topo order."""
    by_id: dict[str, PluginMetadata] = {}
    skipped: dict[str, str] = {}
    for meta in discovered:
        previous = by_id.get(meta.id)
        if previous is not None:
            # Later sources win: search_path < user < entrypoint is not assumed;
            # last occurrence in the discovery list wins, matching scan order.
            skipped[f"{previous.id}@{previous.origin}"] = (
                f"duplicate id {meta.id!r}; later origin {meta.origin} replaces {previous.origin}"
            )
        by_id[meta.id] = meta

    disabled = set(config.disabled)
    enabled_ids = list(config.enabled)
    selected_map: dict[str, PluginMetadata] = {}
    for plugin_id in enabled_ids:
        if plugin_id in disabled:
            skipped[plugin_id] = "disabled"
            continue
        meta = by_id.get(plugin_id)
        if meta is None:
            raise CompositionError(
                f"enabled plugin {plugin_id!r} was not discovered. "
                f"Install it or add its directory to plugins.search_paths."
            )
        selected_map[plugin_id] = meta

    for plugin_id in list(selected_map):
        if plugin_id in disabled:
            selected_map.pop(plugin_id, None)

    # Dependency closure: required plugins must themselves be enabled.
    for meta in list(selected_map.values()):
        for dep in meta.depends:
            if dep.plugin_id in disabled:
                raise CompositionError(
                    f"plugin {meta.id!r} depends on disabled plugin {dep.plugin_id!r}"
                )
            if dep.plugin_id not in selected_map:
                raise CompositionError(
                    f"plugin {meta.id!r} depends on {dep.plugin_id!r}, which is not enabled"
                )
            target = selected_map[dep.plugin_id]
            if dep.version:
                _assert_version(meta.id, target, dep.version)

    ordered = _topo_sort(selected_map)
    service_owners = _unique_services(ordered, config)
    return Composition(
        selected=tuple(ordered),
        discovered=tuple(by_id.values()),
        skipped=skipped,
        service_owners=service_owners,
    )


def _assert_version(dependent: str, target: PluginMetadata, spec: str) -> None:
    try:
        specifier = SpecifierSet(spec)
        version = Version(target.version)
    except InvalidVersion as exc:
        raise PluginError(f"plugin {target.id!r} has an unusable version {target.version!r}") from exc
    except Exception as exc:
        raise CompositionError(
            f"plugin {dependent!r} has an invalid version specifier {spec!r} for {target.id!r}"
        ) from exc
    if version not in specifier:
        raise CompositionError(
            f"plugin {dependent!r} requires {target.id!r} {spec}, found {target.version}"
        )


def _topo_sort(selected: dict[str, PluginMetadata]) -> list[PluginMetadata]:
    temp: set[str] = set()
    perm: set[str] = set()
    order: list[str] = []
    provided_by: dict[str, list[str]] = {}
    for meta in selected.values():
        for spec in meta.provides:
            provided_by.setdefault(spec.name, []).append(meta.id)

    def visit(node: str) -> None:
        if node in perm:
            return
        if node in temp:
            raise CompositionError(f"plugin dependency cycle involving {node!r}")
        temp.add(node)
        meta = selected[node]
        predecessors = {dep.plugin_id for dep in meta.depends if dep.plugin_id in selected}
        for spec in meta.requires:
            if spec.optional:
                continue
            predecessors.update(provided_by.get(spec.name, ()))
        predecessors.discard(node)
        for dep_id in sorted(predecessors):
            if dep_id not in selected:
                continue
            visit(dep_id)
        temp.remove(node)
        perm.add(node)
        order.append(node)

    for plugin_id in sorted(selected):
        visit(plugin_id)
    return [selected[plugin_id] for plugin_id in order]


def _unique_services(
    ordered: list[PluginMetadata],
    config: HostConfig,
) -> dict[str, tuple[str, ...]]:
    owners: dict[str, list[str]] = {}
    uniqueness: dict[str, bool] = {}
    for meta in ordered:
        for spec in meta.provides:
            owners.setdefault(spec.name, []).append(meta.id)
            uniqueness[spec.name] = spec.unique or uniqueness.get(spec.name, False)
    resolved: dict[str, tuple[str, ...]] = {}
    for name, ids in owners.items():
        unique = uniqueness.get(name, True)
        if unique and len(set(ids)) > 1:
            chosen = config.service_selection.get(name)
            if chosen not in ids:
                raise CompositionError(
                    f"service {name!r} is unique but provided by {sorted(set(ids))}. "
                    f"Set [services] {name!r} = \"<plugin-id>\" to select one."
                )
            resolved[name] = (chosen,)
        else:
            resolved[name] = tuple(ids)
    return resolved
