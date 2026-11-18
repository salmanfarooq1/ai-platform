"""A stack's runtime volumes: named in its marker, proven ours by label and driver, removed by exact name, checked gone."""
import json

from scripts.poc_lib.context import StackContext
from scripts.poc_lib.up import PocError

SCRATCH_VOLUMES = ("app_tmp",)  # Compose volumes that hold no data (upload spool): not in the marker, removed only by `destroy`


def present_owned_volumes(context: StackContext, extra: tuple[str, ...] = ()) -> list[str]:
    """The marker's volumes (plus the named scratch ones) that exist now, each proven ours by name, label and kind.
    Refuses before anything is removed."""
    project = str(context.marker["project"])
    names = [str(v) for v in context.marker["volumes"]] + [f"{project}_{name}" for name in extra]
    if not project.startswith("ai-platform-poc-"):
        raise PocError("refusing a volume outside a POC project")
    present = []
    for name in names:
        if not name.startswith(project + "_") or name.startswith("ai-platform_"):
            raise PocError(f"refusing volume {name}: it is not named for this stack")
        result = context.runner.run(["docker", "volume", "inspect", name], env=context.env, check=False)
        if result.returncode != 0:
            continue  # already gone
        try:
            info = json.loads(result.text)[0]
        except (ValueError, IndexError):
            raise PocError(f"refusing volume {name}: it cannot be inspected") from None
        labels = info.get("Labels") or {}
        if labels.get("com.docker.compose.project") != project:
            raise PocError(f"refusing volume {name}: it is not labelled as a volume of {project}")
        if info.get("Driver") != "local" or info.get("Options"):
            raise PocError(f"refusing volume {name}: it is not a plain Docker-managed volume")
        present.append(name)
    return present


def remove_owned_volumes(context: StackContext, extra: tuple[str, ...] = ()) -> None:
    """Remove this stack's runtime volumes (containers must already be gone). Every removal is tried; any that fails, or
    leaves its volume behind, fails the whole step: a caller never reports success over data that is still there."""
    names = present_owned_volumes(context, extra)
    failed = []
    for name in names:
        if context.runner.run(["docker", "volume", "rm", name], env=context.env, check=False).returncode != 0:
            failed.append(name)
    still_there = [name for name in names
                   if context.runner.run(["docker", "volume", "inspect", name], env=context.env, check=False).returncode == 0]
    if failed or still_there:
        raise PocError("could not remove runtime volume(s): " + ", ".join(sorted(set(failed) | set(still_there))))
