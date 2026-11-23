# Copyright: 2007 MoinMoin:ThomasWaldmann
# License: GNU GPL v2 (or any later version), see LICENSE.txt for details.

"""
MoinMoin - moin.utils.diff_text tests.
"""

import pytest

from moin.utils import diff_text


class TestDiffText:

    def testDiff(self):
        """utils.diff_text.diff: test correct diff calculation."""
        in1 = """AAA 001
AAA 002
AAA 003
AAA 004
AAA 005
AAA 006
AAA 007
AAA 008
AAA 009
AAA 010
AAA 011
AAA 012
AAA 013
AAA 014
"""

        in2 = """AAA 001
AAA 002
AAA 005
AAA 006
AAA 007
AAA 008
BBB 001
BBB 002
AAA 009
AAA 010
BBB 003
"""

        result = diff_text.diff(in1.splitlines(), in2.splitlines())
        result = "\n".join(result)

        expected = """\
  AAA 001
  AAA 002
- AAA 003
- AAA 004
  AAA 005
  AAA 006
  AAA 007
  AAA 008
+ BBB 001
+ BBB 002
  AAA 009
  AAA 010
+ BBB 003
- AAA 011
- AAA 012
- AAA 013
- AAA 014"""

        assert result == expected, 'Expected "%(expected)s" but got "%(result)s"' % locals()


@pytest.mark.parametrize("ignorews", [False, True])
@pytest.mark.parametrize("lines", [[], ["same\n"], ["Привіт\n", "  text with whitespace\n"]])
def test_identical_lists_return_empty_without_modifying_inputs(lines, ignorews):
    oldlines = lines.copy()
    newlines = lines.copy()

    assert oldlines is not newlines
    assert diff_text.diff(oldlines, newlines, ignorews=ignorews) == []
    assert oldlines == newlines == lines


@pytest.mark.parametrize("ignorews", [False, True])
@pytest.mark.parametrize(
    "oldlines, newlines, expected",
    [
        ([], ["new\n"], ["+ new\n"]),
        (["old\n"], [], ["- old\n"]),
        (["old\n"], ["new\n"], ["- old\n", "+ new\n"]),
        (["same\n", "old\n"], ["same\n", "new\n"], ["  same\n", "- old\n", "+ new\n"]),
    ],
)
def test_changed_lists_keep_expected_diff(oldlines, newlines, expected, ignorews):
    assert diff_text.diff(oldlines, newlines, ignorews=ignorews) == expected


def test_equal_tuples_keep_existing_sequence_support():
    assert diff_text.diff(("same\n", "text\n"), ("same\n", "text\n")) == []


coverage_modules = ["moin.utils.diff_text"]
