import tempfile
import unittest
from pathlib import Path
from unittest import mock

import transcriber_core


class ResolveHomrDirTests(unittest.TestCase):
    def test_prefers_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / "custom-homr"
            env_path.mkdir()

            with mock.patch.dict("os.environ", {"HOMR_DIR": str(env_path)}, clear=False):
                resolved = transcriber_core.resolve_homr_dir()

        self.assertEqual(resolved, env_path.resolve())

    def test_uses_repo_sibling_homr_when_present(self) -> None:
        repo_parent = transcriber_core.BASE_DIR.parent

        def fake_exists(path: Path) -> bool:
            return path == (repo_parent / transcriber_core.DEFAULT_HOMR_DIR_NAME)

        with mock.patch.dict("os.environ", {}, clear=False):
            with mock.patch("pathlib.Path.exists", autospec=True, side_effect=fake_exists):
                resolved = transcriber_core.resolve_homr_dir()

        self.assertEqual(resolved, (repo_parent / transcriber_core.DEFAULT_HOMR_DIR_NAME).resolve())

    def test_falls_back_to_repo_sibling_path_when_missing(self) -> None:
        expected = (transcriber_core.BASE_DIR.parent / transcriber_core.DEFAULT_HOMR_DIR_NAME).resolve()

        with mock.patch.dict("os.environ", {}, clear=False):
            with mock.patch("pathlib.Path.exists", autospec=True, return_value=False):
                resolved = transcriber_core.resolve_homr_dir()

        self.assertEqual(resolved, expected)


class CheckHomrInstallationTests(unittest.TestCase):
    def setUp(self) -> None:
        transcriber_core._homr_check_cache.update({"checked_at": 0.0, "value": False})

    def test_returns_false_when_homr_dir_missing(self) -> None:
        with mock.patch.object(transcriber_core, "resolve_homr_dir", return_value=Path("/missing/homr")):
            with mock.patch("pathlib.Path.exists", autospec=True, return_value=False):
                self.assertFalse(transcriber_core.check_homr_installation(force_refresh=True))

    def test_invokes_poetry_from_resolved_homr_dir(self) -> None:
        homr_dir = Path("/tmp/homr")

        completed = mock.Mock(returncode=0)
        with mock.patch.object(transcriber_core, "resolve_homr_dir", return_value=homr_dir):
            with mock.patch("pathlib.Path.exists", autospec=True, return_value=True):
                with mock.patch("subprocess.run", return_value=completed) as run_mock:
                    self.assertTrue(transcriber_core.check_homr_installation(force_refresh=True))

        run_mock.assert_called_once_with(
            ["poetry", "run", "homr", "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=homr_dir,
        )


if __name__ == "__main__":
    unittest.main()
