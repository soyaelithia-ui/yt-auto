"""Adversarial stress test for 64-bit SimHash deduplication and lease concurrency."""

import concurrent.futures
import time
from pathlib import Path
import pytest

from src.core.repository import (
    QueueRepository,
    compute_simhash_64,
    simhash_hamming_distance,
    is_simhash_duplicate,
    to_signed_64,
    to_unsigned_64,
    connect,
)
from src.db import is_story_duplicate


@pytest.mark.unit
class TestSimHashAdversarialStress:
    """Adversarial testing of SimHash 64-bit fingerprinting and Hamming distance."""

    def test_simhash_exact_duplicates_zero_distance(self):
        text_a = "Había una criatura en el bosque oscuro que me observaba fijamente desde los árboles."
        text_b = "Había una criatura en el bosque oscuro que me observaba fijamente desde los árboles."

        hash_a = compute_simhash_64(text_a)
        hash_b = compute_simhash_64(text_b)

        assert hash_a != 0
        assert hash_a == hash_b
        assert simhash_hamming_distance(hash_a, hash_b) == 0
        assert is_simhash_duplicate(hash_a, hash_b, max_distance=0) is True
        assert is_simhash_duplicate(hash_a, hash_b, max_distance=3) is True

    def test_simhash_near_duplicates_word_swaps_and_formatting(self):
        """Word order swaps, formatting, punctuation adjustments should yield Hamming distance <= 3 bits."""
        base_story = (
            "Mi abuelo solía contarme historias sobre el viejo faro en el acantilado norte. "
            "Decía que en las noches de tormenta una extraña luz verde brillaba desde la torre abandonada. "
            "Nadie vivía allí desde 1943 cuando el último farero desapareció misteriosamente. "
            "El verano pasado decidí visitar el acantilado junto a mis amigos Lucas y Sofía para acampar. "
            "Al llegar las olas rompían con furia contra las rocas oscuras y la puerta estaba entreabierta. "
            "Entramos con cautela mientras la tarde caía y las escaleras de caracol crujían bajo nuestros pasos. "
            "En el tercer piso encontramos una mesa con candelabro cubierto de polvo denso. "
            "De repente la puerta inferior se cerró de golpe con un estruendo ensordecedor en la oscuridad."
        )
        # Variant 1: Word order swap (Lucas y Sofía -> Sofía y Lucas)
        variant_swap = base_story.replace("Lucas y Sofía", "Sofía y Lucas")

        # Variant 2: Punctuation & case alterations
        variant_punct = base_story.replace(".", "!").replace(",", "")

        # Variant 3: Whitespace padding
        variant_ws = base_story + "\n\n   \t  \n"

        h_base = compute_simhash_64(base_story)
        h_swap = compute_simhash_64(variant_swap)
        h_punct = compute_simhash_64(variant_punct)
        h_ws = compute_simhash_64(variant_ws)

        dist_swap = simhash_hamming_distance(h_base, h_swap)
        dist_punct = simhash_hamming_distance(h_base, h_punct)
        dist_ws = simhash_hamming_distance(h_base, h_ws)

        assert dist_swap <= 3, f"Expected swap Hamming distance <= 3, got {dist_swap}"
        assert dist_punct <= 3, f"Expected punct Hamming distance <= 3, got {dist_punct}"
        assert dist_ws <= 3, f"Expected whitespace Hamming distance <= 3, got {dist_ws}"

        assert is_simhash_duplicate(h_base, h_swap, max_distance=3) is True
        assert is_simhash_duplicate(h_base, h_punct, max_distance=3) is True
        assert is_simhash_duplicate(h_base, h_ws, max_distance=3) is True

    def test_simhash_completely_different_texts(self):
        """Completely different story topics should yield Hamming distance > 3 bits (typically 20-40 bits)."""
        horror_text = (
            "Escuché pasos en el ático a las 3 de la madrugada. Cuando subí la escalera de madera, "
            "encontré una silueta alta y esquelética con ojos rojos brillantes sosteniendo un cuchillo oxidado."
        )
        aita_text = (
            "Soy el malo por no querer prestarle los ahorros de mi boda a mi cuñada para sus vacaciones? "
            "Mi esposa dice que la familia va primero pero yo creo que ella es irresponsable con sus finanzas."
        )
        scp_text = (
            "SCP-173 está compuesto de hormigón y barras de refuerzo con rastros de pintura Krylon. "
            "Permanece inmóvil cuando se le observa fijamente y ataca fracturando el cuello en la base del cráneo."
        )

        h_horror = compute_simhash_64(horror_text)
        h_aita = compute_simhash_64(aita_text)
        h_scp = compute_simhash_64(scp_text)

        dist_horror_aita = simhash_hamming_distance(h_horror, h_aita)
        dist_horror_scp = simhash_hamming_distance(h_horror, h_scp)
        dist_aita_scp = simhash_hamming_distance(h_aita, h_scp)

        assert dist_horror_aita > 3, f"Expected dist > 3, got {dist_horror_aita}"
        assert dist_horror_scp > 3, f"Expected dist > 3, got {dist_horror_scp}"
        assert dist_aita_scp > 3, f"Expected dist > 3, got {dist_aita_scp}"

        assert is_simhash_duplicate(h_horror, h_aita, max_distance=3) is False
        assert is_simhash_duplicate(h_horror, h_scp, max_distance=3) is False

    def test_simhash_boundary_and_corner_inputs(self):
        """Test empty, None, single-char, massive text, and unsigned/signed conversion."""
        assert compute_simhash_64("") == 0
        assert compute_simhash_64(None) == 0
        assert compute_simhash_64("   \n\t  ") == 0
        assert compute_simhash_64("!@#$%^&*()") == 0

        single_char = compute_simhash_64("a")
        assert single_char != 0
        assert 0 <= single_char <= 0xFFFFFFFFFFFFFFFF

        # Massive text
        massive = "relato de terror en la oscuridad con sombras y fantasmas " * 2000
        h_massive = compute_simhash_64(massive)
        assert h_massive != 0

        # Signed vs Unsigned 64-bit conversion round-trip
        for val in [0, 1, 0x7FFFFFFFFFFFFFFF, 0x8000000000000000, 0xFFFFFFFFFFFFFFFF]:
            signed = to_signed_64(val)
            unsigned = to_unsigned_64(signed)
            assert unsigned == (val & 0xFFFFFFFFFFFFFFFF)

    def test_repository_simhash_duplicate_detection(self, tmp_path):
        """Test QueueRepository fingerprint recording and duplicate check with SimHash."""
        db_file = tmp_path / "test_simhash.db"
        repo = QueueRepository(str(db_file))
        repo.initialize()

        story_text_1 = (
            "Mi abuelo solía contarme historias sobre el viejo faro en el acantilado norte. "
            "Decía que en las noches de tormenta una extraña luz verde brillaba desde la torre abandonada. "
            "Nadie vivía allí desde 1943 cuando el último farero desapareció misteriosamente. "
            "El verano pasado decidí visitar el acantilado junto a mis amigos Lucas y Sofía para acampar. "
            "Al llegar las olas rompían con furia contra las rocas oscuras y la puerta estaba entreabierta."
        )
        story_id = "story_faro_1"
        repo.enqueue(story_id, "El viejo faro", story_text_1, "https://x/faro1", "moku")

        # Register original fingerprint
        h1 = compute_simhash_64(story_text_1)
        repo.record_fingerprint(
            run_id="run_orig",
            story_id=story_id,
            channel="moku",
            kind="script",
            payload=story_text_1,
            normalized_text=story_text_1,
            simhash=h1,
        )

        # Check duplicate with identical text
        assert is_story_duplicate("moku", "Otro Título", story_text_1, db_path=str(db_file)) is True

        # Check duplicate with word order swap (detected via SimHash Hamming <= 3)
        story_text_near = story_text_1.replace("Lucas y Sofía", "Sofía y Lucas")
        assert is_story_duplicate("moku", "Título Diferente", story_text_near, db_path=str(db_file)) is True

        # Check different story is NOT duplicate
        story_diff = "Hoy cociné una deliciosa lasaña italiana para toda mi familia en la fiesta de cumpleaños."
        assert is_story_duplicate("moku", "Receta", story_diff, db_path=str(db_file)) is False


@pytest.mark.unit
class TestLeaseConcurrencyStress:
    """Stress-test lease acquisition, renewals, collisions, and expiration recovery."""

    def test_concurrent_lease_claims_on_same_job(self, tmp_path):
        """When 20 workers simultaneously attempt to claim the exact same job, exactly 1 wins."""
        db_file = tmp_path / "test_leases.db"
        repo = QueueRepository(str(db_file))
        repo.initialize()

        # Enqueue a test story
        repo.enqueue(
            "job_stress_001",
            "Historia Concurrente",
            "Contenido de prueba para estrés de leases",
            "https://example.com/job_stress_001",
            "moku",
        )

        results = []
        num_workers = 20

        def worker_attempt(worker_id: int):
            worker_repo = QueueRepository(str(db_file))
            owner = f"worker_{worker_id}"
            # Attempt to claim exact job_stress_001
            lease = worker_repo.claim_exact(
                story_id="job_stress_001",
                channel="moku",
                owner=owner,
                lease_seconds=300,
            )
            return (worker_id, lease)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker_attempt, i) for i in range(num_workers)]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        successful_claims = [w for w, lease in results if lease is not None]
        failed_claims = [w for w, lease in results if lease is None]

        assert len(successful_claims) == 1, f"Expected exactly 1 claim, got {len(successful_claims)}: {successful_claims}"
        assert len(failed_claims) == num_workers - 1

    def test_lease_heartbeat_renewal_and_collision_rejection(self, tmp_path):
        """Active lease owner can heartbeat/extend lease; other workers are rejected."""
        db_file = tmp_path / "test_lease_renewal.db"
        repo = QueueRepository(str(db_file))
        repo.initialize()

        repo.enqueue(
            "job_renew_001",
            "Historia Renewal",
            "Contenido para renovación de leases",
            "https://example.com/job_renew_001",
            "moku",
        )

        owner = "worker_alpha"

        # Initial claim
        claimed = repo.claim_exact(
            story_id="job_renew_001",
            channel="moku",
            owner=owner,
            lease_seconds=100,
        )
        assert claimed is not None
        run_id = claimed["run_id"]

        # Heartbeat / renew lease by owner
        heartbeat_ok = repo.heartbeat(
            run_id=run_id,
            owner=owner,
            lease_seconds=500,
        )
        assert heartbeat_ok is True

        # Another worker tries to heartbeat with wrong owner -> rejected
        fake_heartbeat = repo.heartbeat(
            run_id=run_id,
            owner="worker_imposter",
            lease_seconds=500,
        )
        assert fake_heartbeat is False

        # Another worker tries to claim exact job while active -> rejected
        other_claim = repo.claim_exact(
            story_id="job_renew_001",
            channel="moku",
            owner="worker_beta",
            lease_seconds=500,
        )
        assert other_claim is None

    def test_expired_lease_recovery_and_reacquisition(self, tmp_path):
        """Expired lease can be recovered and acquired by another worker."""
        db_file = tmp_path / "test_lease_expiry.db"
        repo = QueueRepository(str(db_file))
        repo.initialize()

        repo.enqueue(
            "job_expire_001",
            "Historia Expiración",
            "Contenido para expiración de leases",
            "https://example.com/job_expire_001",
            "moku",
        )

        now_base = int(time.time())

        # Acquire with short lease (expires in 10s at now_base + 10)
        lease1 = repo.claim_exact(
            story_id="job_expire_001",
            channel="moku",
            owner="worker_old",
            lease_seconds=10,
            now=now_base,
        )
        assert lease1 is not None

        # At now_base + 5 (before expiration), recovery does nothing
        rec_before = repo.recover_expired_leases(now=now_base + 5)
        assert rec_before == 0

        # At now_base + 20 (after expiration), recovery resets the lease
        rec_after = repo.recover_expired_leases(now=now_base + 20)
        assert rec_after >= 1

        # Now worker_new can claim the story cleanly
        lease2 = repo.claim_exact(
            story_id="job_expire_001",
            channel="moku",
            owner="worker_new",
            lease_seconds=300,
            now=now_base + 25,
        )
        assert lease2 is not None
