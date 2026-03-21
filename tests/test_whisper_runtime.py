from __future__ import annotations

from unittest.mock import MagicMock

from osk.whisper_runtime import WhisperProfile, WhisperRuntimeManager, _parse_profile_ladder


def test_parse_profile_ladder_ignores_invalid_tokens() -> None:
    profiles = _parse_profile_ladder("large-v3:cuda:float16,invalid,small:cpu:int8")

    assert profiles == [
        WhisperProfile("large-v3", "cuda", "float16"),
        WhisperProfile("small", "cpu", "int8"),
    ]


def test_runtime_manager_falls_back_when_first_profile_fails() -> None:
    calls = []

    def factory(profile: WhisperProfile):
        calls.append(profile.label)
        if profile.device == "cuda":
            raise RuntimeError("cuda unavailable")
        model = MagicMock()
        model.transcribe.return_value = ([], MagicMock())
        return model

    manager = WhisperRuntimeManager(
        profiles=[
            WhisperProfile("large-v3", "cuda", "float16"),
            WhisperProfile("large-v3", "cpu", "int8"),
        ],
        model_factory=factory,
    )

    manager.ensure_loaded_sync()

    assert manager.active_profile == WhisperProfile("large-v3", "cpu", "int8")
    assert calls == ["large-v3:cuda:float16", "large-v3:cpu:int8"]


def test_runtime_manager_downgrades_on_cuda_oom() -> None:
    first_model = MagicMock()
    first_model.transcribe.side_effect = RuntimeError("CUDA out of memory on device")
    second_model = MagicMock()
    second_model.transcribe.return_value = (["segment"], MagicMock())

    def factory(profile: WhisperProfile):
        if profile.device == "cuda":
            return first_model
        return second_model

    manager = WhisperRuntimeManager(
        profiles=[
            WhisperProfile("large-v3", "cuda", "float16"),
            WhisperProfile("medium", "cpu", "int8"),
        ],
        model_factory=factory,
    )

    result = manager.transcribe_sync(object(), language="en")

    assert manager.active_profile == WhisperProfile("medium", "cpu", "int8")
    assert manager.last_fallback_reason == "cuda_oom"
    assert result == (["segment"], second_model.transcribe.return_value[1])
