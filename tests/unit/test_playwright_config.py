import json
import os
import shlex
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


def test_poetry_resolves_from_environment(tmp_path):
    config = (ROOT / "ui/playwright.config.ts").read_text()
    assert "/home/ubuntu/" not in config
    path_bin = tmp_path / "bin"
    path_bin.mkdir()
    path_poetry = path_bin / "poetry"
    override = tmp_path / "poetry with spaces"
    for executable in (path_poetry, override):
        executable.write_text("#!/bin/sh\nexit 0\n")
        executable.chmod(0o755)
    program = '''
const ts = require('typescript'), fs = require('fs'), Module = require('module'), path = require('path');
const file = path.resolve('playwright.config.ts');
const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
const m = new Module(file, module); m.filename = file; m.paths = Module._nodeModulePaths(path.dirname(file)); m._compile(code, file);
console.log(JSON.stringify(m.exports.default.webServer.filter(x => x.command.includes('--reference-company')).map(x => x.command)));
'''
    for showcase in (False, True):
        for selected in (path_poetry, override):
            env = dict(os.environ, PATH=str(path_bin) + os.pathsep + os.environ["PATH"])
            env.pop("POETRY", None)
            if selected == override:
                env["POETRY"] = str(override)
            args = ["node", "-e", program]
            if showcase:
                args.extend(["--", "--project=showcase-m0"])
            result = subprocess.run(args, cwd=ROOT / "ui", env=env, text=True, capture_output=True)
            assert result.returncode == 0, result.stderr
            commands = json.loads(result.stdout)
            assert len(commands) == 1
            assert shlex.split(commands[0])[0] == str(selected)
    env = dict(os.environ, POETRY=str(tmp_path / "missing"))
    result = subprocess.run(["node", "-e", program], cwd=ROOT / "ui", env=env, text=True, capture_output=True)
    assert result.returncode != 0 and "poetry executable not found" in result.stderr.lower()


def test_poetry_override_is_used_by_all_python_servers(tmp_path):
    override = tmp_path / 'poetry with spaces'
    override.write_text('#!/bin/sh\nexit 0\n')
    override.chmod(0o755)
    program = '''
const ts = require('typescript'), fs = require('fs'), Module = require('module'), path = require('path');
const file = path.resolve('playwright.config.ts');
const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
const m = new Module(file, module); m.filename = file; m.paths = Module._nodeModulePaths(path.dirname(file)); m._compile(code, file);
console.log(JSON.stringify(m.exports.default.webServer.map(x => x.command).filter(x => x.includes('scripts/e2e/serve.py'))));
'''
    result = subprocess.run(['node', '-e', program], cwd=ROOT / 'ui', env=dict(os.environ, POETRY=str(override)), text=True, capture_output=True, check=True)
    commands = json.loads(result.stdout)
    assert len(commands) == 4
    assert all(shlex.split(command)[0] == str(override) for command in commands)
