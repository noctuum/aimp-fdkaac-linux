import os
import zipfile

from tools.aimppack import Member, write_zip

EPOCH = 1791714862


def members(tmp_path):
    (tmp_path / "a").write_bytes(b"x")
    (tmp_path / "b").write_text("y")
    return [Member("enc_x/", None, 0o755), Member("enc_x/a", tmp_path / "a", 0o755), Member("enc_x/b.txt", tmp_path / "b", 0o644)]


def test_members_keep_order_and_modes(tmp_path):
    dest = tmp_path / "p.zip"
    write_zip(dest, members(tmp_path), EPOCH)
    with zipfile.ZipFile(dest) as z:
        infos = z.infolist()
        assert [i.filename for i in infos] == ["enc_x/", "enc_x/a", "enc_x/b.txt"]
        assert [(i.external_attr >> 16) & 0o7777 for i in infos] == [0o755, 0o755, 0o644]
        assert {i.create_system for i in infos} == {3} and infos[0].is_dir()
        assert z.read("enc_x/a") == b"x"


def test_same_members_give_the_same_bytes(tmp_path):
    first, second = tmp_path / "1.zip", tmp_path / "2.zip"
    m = members(tmp_path)
    write_zip(first, m, EPOCH)
    os.utime(tmp_path / "a", (0, 0))
    write_zip(second, m, EPOCH)
    assert first.read_bytes() == second.read_bytes()
