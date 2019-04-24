from solo.client import SoloClient
from solo.commands import SoloBootloader, SoloExtension

from fido2.ctap1 import ApduError
from fido2.utils import sha256

from .util import shannon_entropy
from .tester import Tester, Test


class SoloTests(Tester):
    def __init__(self, tester=None):
        super().__init__(tester)

    def run(self,):
        self.test_solo()

    def test_solo(self,):
        """
        Solo specific tests
        """
        # RNG command
        sc = SoloClient()
        sc.find_device(self.dev)
        sc.use_u2f()
        memmap = (0x08005000, 0x08005000 + 198 * 1024 - 8)

        total = 1024 * 16
        with Test("Gathering %d random bytes..." % total):
            entropy = b""
            while len(entropy) < total:
                entropy += sc.get_rng()

        with Test("Test entropy is close to perfect"):
            s = shannon_entropy(entropy)
            assert s > 7.98
        print("Entropy is %.5f bits per byte." % s)

        with Test("Test Solo version command"):
            assert len(sc.solo_version()) == 3

        with Test("Test bootloader is not active"):
            try:
                sc.write_flash(memmap[0], b"1234")
            except ApduError:
                pass

        sc.exchange = sc.exchange_fido2

        req = SoloClient.format_request(SoloExtension.version, 0, b"A" * 16)
        assertions, client_data = sc.client.get_assertion(
            sc.host, "B" * 32, [{"id": req, "type": "public-key"}]
        )

        with Test("Test custom command returned valid assertion"):
            assert len(assertions) == 1
            a = assertions[0]
            assert a.auth_data.rp_id_hash == sha256(sc.host.encode("utf8"))
            assert a.credential["id"] == req
            assert (a.auth_data.flags & 0x5) == 0x5

        with Test("Test Solo version and random commands with fido2 layer"):
            assert len(sc.solo_version()) == 3
            sc.get_rng()

    def test_bootloader(self,):
        sc = SoloClient()
        sc.find_device(self.dev)
        sc.use_u2f()

        memmap = (0x08005000, 0x08005000 + 198 * 1024 - 8)
        data = b"A" * 64

        with Test("Test version command"):
            assert len(sc.bootloader_version()) == 3

        with Test("Test write command"):
            sc.write_flash(memmap[0], data)

        for addr in (memmap[0] - 8, memmap[0] - 4, memmap[1], memmap[1] - 8):
            with Test("Test out of bounds write command at 0x%04x" % addr):
                try:
                    sc.write_flash(addr, data)
                except CtapError as e:
                    assert e.code == CtapError.ERR.NOT_ALLOWED
