from application.world.services.character_naming import (
    CLICHE_SURNAMES,
    build_character_surname_seed,
    infer_surname,
)


def test_surname_seed_avoids_cliche_surnames():
    seed = build_character_surname_seed(12, rng_seed="novel-a")

    assert len(seed.surnames) == 12
    assert not set(seed.surnames) & set(CLICHE_SURNAMES)


def test_surname_seed_is_deterministic_with_seed():
    left = build_character_surname_seed(8, rng_seed="same-premise")
    right = build_character_surname_seed(8, rng_seed="same-premise")

    assert left.surnames == right.surnames


def test_surname_seed_is_unique_when_pool_is_sufficient():
    seed = build_character_surname_seed(20, rng_seed="wide-cast")

    assert len(seed.surnames) == len(set(seed.surnames))


def test_infer_surname_prefers_compound_surname():
    assert infer_surname("欧阳照夜") == "欧阳"
    assert infer_surname("顾照夜") == "顾"
