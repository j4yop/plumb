"""Reading one recording: the metadata parse and the raw tracking reader.

The fixtures here are hand-written, not excerpts of the licensed data: a three-line ATD file
and a two-team metadata document are enough to pin down the two contracts that matter —
the track-slot-to-team mapping and ``video_frame = frame_id - 1``.
"""

import numpy as np
import pytest

from mtah.config import DEFAULT
from mtah.match import parse_meta, parse_smart_tagging, read_atd

# --------------------------------------------------------------------------------------------------
# Fixtures written to disk
# --------------------------------------------------------------------------------------------------

# The team ids are deliberately in the opposite order to their appearance in the document:
# "team_b" comes first and is therefore the home team. A parser that sorted by id, or that
# guessed from the name, would get this wrong.
META_XML = """<?xml version="1.0" encoding="utf-8"?>
<main>
  <Metadata>
    <GlobalConfig>
      <FrameRate>25.0</FrameRate>
    </GlobalConfig>
    <Sessions>
      <Session id="session1">
        <MatchParameters>
          <Score idLocalTeam="team_b" idVisitingTeam="team_a"/>
        </MatchParameters>
        <FieldSize>
          <Width>105</Width>
          <Height>68</Height>
        </FieldSize>
        <Teams>
          <Team id="team_b">
            <Name>Alpha FC</Name>
            <ProviderTeamsParameters>
              <ProviderParameter>
                <Name>attack_direction_first_half</Name>
                <Value>left_to_right</Value>
              </ProviderParameter>
            </ProviderTeamsParameters>
          </Team>
          <Team id="team_a">
            <Name>Beta United</Name>
            <ProviderTeamsParameters>
              <ProviderParameter>
                <Name>attack_direction_first_half</Name>
                <Value>right_to_left</Value>
              </ProviderParameter>
            </ProviderTeamsParameters>
          </Team>
        </Teams>
        <PlayerList>
          <Player id="1" teamId="team_b"><Name>Track 1</Name><ShirtNumber>1</ShirtNumber></Player>
          <Player id="2" teamId="team_b"><Name>Track 2</Name><ShirtNumber>2</ShirtNumber></Player>
          <Player id="3" teamId="team_a"><Name>Track 3</Name><ShirtNumber>3</ShirtNumber></Player>
          <Player id="4" teamId="team_a"><Name>Track 4</Name><ShirtNumber>4</ShirtNumber></Player>
        </PlayerList>
      </Session>
    </Sessions>
  </Metadata>
</main>
"""

# Three ATD frames, four slots each. `NaN` groups are missing observations.
RAW_LINES = [
    "1:0.1,0.2,1.0;0.5,0.5,NaN;NaN,NaN,NaN;0.9,0.1,0.0:0.3,0.4,2.0",
    "2:0.2,0.4,1.5;NaN,NaN,NaN;NaN,NaN,NaN;0.8,0.2,0.5:0.6,0.8,3.0",
    "3:0.3,0.6,2.0;NaN,NaN,NaN;NaN,NaN,NaN;NaN,NaN,NaN:NaN,NaN,NaN",
]

SMART_TAGGING_XML = """<?xml version="1.0" ?>
<file>
  <ALL_INSTANCES>
    <instance>
      <ID>2</ID>
      <start>40.0</start>
      <end>44.0</end>
      <code>SET PIECES</code>
      <label><group>Team</group><text>N/A</text></label>
      <label><group>Type</group><text>Kick Off (Start)</text></label>
      <label><group>Half</group><text>1st Half</text></label>
    </instance>
    <instance>
      <ID>1</ID>
      <start>10.0</start>
      <end>45.0</end>
      <code>SET PIECES</code>
      <label><group>Team</group><text>N/A</text></label>
      <label><group>Type</group><text>Corner</text></label>
    </instance>
  </ALL_INSTANCES>
</file>
"""


@pytest.fixture
def meta_path(tmp_path):
    path = tmp_path / "match_atd.xml"
    path.write_text(META_XML, encoding="utf-8")
    return str(path)


@pytest.fixture
def raw_path(tmp_path):
    path = tmp_path / "match_atd.txt"
    path.write_text("\n".join(RAW_LINES) + "\n", encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------------------------------
# parse_meta
# --------------------------------------------------------------------------------------------------


def test_parse_meta_returns_the_team_names_in_document_order(meta_path):
    names, _slot_team = parse_meta(meta_path)
    assert names == ("Alpha FC", "Beta United")
    assert names[0] == "Alpha FC"  # the first team in the metadata is home


def test_parse_meta_maps_every_slot_to_its_team(meta_path):
    _names, slot_team = parse_meta(meta_path)
    assert slot_team.shape == (4,)
    assert slot_team.dtype == np.int8
    # slots 1 and 2 are Alpha FC (home = 0), slots 3 and 4 are Beta United (away = 1)
    assert slot_team.tolist() == [0, 0, 1, 1]


def test_parse_meta_follows_document_order_not_the_team_id(meta_path):
    """The ids sort the other way round; the mapping must not depend on them."""
    names, slot_team = parse_meta(meta_path)
    assert names[0] == "Alpha FC"  # the team with the *larger* id
    assert slot_team[0] == 0


def test_parse_meta_rejects_a_metadata_with_one_team(tmp_path):
    path = tmp_path / "one_team.xml"
    path.write_text(
        """<?xml version="1.0"?>
        <main><Metadata><Teams>
          <Team id="team_b"><Name>Alpha FC</Name></Team>
        </Teams></Metadata></main>
        """,
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="expected 2 teams"):
        parse_meta(str(path))


def test_parse_meta_rejects_a_player_with_an_unknown_team(tmp_path):
    path = tmp_path / "bad_team.xml"
    path.write_text(
        """<?xml version="1.0"?>
        <main><Metadata>
          <Teams>
            <Team id="team_b"><Name>Alpha FC</Name></Team>
            <Team id="team_a"><Name>Beta United</Name></Team>
          </Teams>
          <PlayerList>
            <Player id="1" teamId="team_b"><Name>Track 1</Name></Player>
            <Player id="2" teamId="team_zzz"><Name>Track 2</Name></Player>
          </PlayerList>
        </Metadata></main>
        """,
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown team"):
        parse_meta(str(path))


def test_parse_meta_rejects_a_metadata_with_no_players(tmp_path):
    path = tmp_path / "no_players.xml"
    path.write_text(
        """<?xml version="1.0"?>
        <main><Metadata><Teams>
          <Team id="team_b"><Name>Alpha FC</Name></Team>
          <Team id="team_a"><Name>Beta United</Name></Team>
        </Teams></Metadata></main>
        """,
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no track slots"):
        parse_meta(str(path))


# --------------------------------------------------------------------------------------------------
# read_atd
# --------------------------------------------------------------------------------------------------


def test_read_atd_converts_normalised_coordinates_to_metres(raw_path):
    arrays = read_atd(raw_path, 4, DEFAULT)

    length = DEFAULT.pitch_length_m
    width = DEFAULT.pitch_width_m

    # frame id 1 -> row 0 -> the first video frame.
    assert arrays["player_xy"][0, 0, 0] == pytest.approx(0.1 * length, abs=1e-4)
    assert arrays["player_xy"][0, 0, 1] == pytest.approx(0.2 * width, abs=1e-4)
    assert arrays["player_xy"][0, 1, 0] == pytest.approx(0.5 * length, abs=1e-4)
    assert arrays["player_xy"][0, 1, 1] == pytest.approx(0.5 * width, abs=1e-4)
    assert arrays["player_xy"][0, 3, 0] == pytest.approx(0.9 * length, abs=1e-4)
    assert arrays["player_xy"][0, 3, 1] == pytest.approx(0.1 * width, abs=1e-4)

    assert arrays["ball_xy"][0, 0] == pytest.approx(0.3 * length, abs=1e-4)
    assert arrays["ball_xy"][0, 1] == pytest.approx(0.4 * width, abs=1e-4)


def test_read_atd_reads_the_speeds(raw_path):
    arrays = read_atd(raw_path, 4, DEFAULT)
    assert arrays["player_speed"][0, 0] == pytest.approx(1.0)
    assert arrays["player_speed"][0, 3] == pytest.approx(0.0)
    assert arrays["ball_speed"][0] == pytest.approx(2.0)
    assert arrays["ball_speed"][1] == pytest.approx(3.0)


def test_read_atd_keeps_missing_observations_as_nan(raw_path):
    arrays = read_atd(raw_path, 4, DEFAULT)
    # slot 3 of the third frame and slot 2 of every frame were never observed.
    assert np.isnan(arrays["player_xy"][0, 2, 0])
    assert np.isnan(arrays["player_xy"][0, 2, 1])
    assert np.isnan(arrays["player_speed"][0, 2])
    # a group with a NaN speed keeps the position.
    assert np.isnan(arrays["player_speed"][0, 1])
    assert not np.isnan(arrays["player_xy"][0, 1, 0])
    # the ball of the third frame was never observed.
    assert np.isnan(arrays["ball_xy"][2, 0])
    assert np.isnan(arrays["ball_xy"][2, 1])


def test_read_atd_maps_the_atd_frame_id_to_the_video_frame(raw_path):
    """video_frame = frame_id - 1: the tracking is already on the video timeline."""
    arrays = read_atd(raw_path, 4, DEFAULT)
    assert arrays["player_xy"].shape[0] == 3
    assert arrays["ball_xy"].shape[0] == 3

    length = DEFAULT.pitch_length_m
    width = DEFAULT.pitch_width_m
    # ATD frame 1 is video frame 0, ATD frame 2 is video frame 1, and so on.
    assert arrays["ball_xy"][0, 0] == pytest.approx(0.3 * length, abs=1e-4)
    assert arrays["ball_xy"][0, 1] == pytest.approx(0.4 * width, abs=1e-4)
    assert arrays["ball_xy"][1, 0] == pytest.approx(0.6 * length, abs=1e-4)
    assert arrays["player_xy"][1, 0, 0] == pytest.approx(0.2 * length, abs=1e-4)
    # The third ATD frame is video frame 2. Its ball was never observed, which is how we
    # know the rows are the frames and not the frame ids.
    assert np.isnan(arrays["ball_xy"][2, 0])
    assert arrays["player_xy"][2, 0, 0] == pytest.approx(0.3 * length, abs=1e-4)
    assert arrays["player_xy"][2, 0, 1] == pytest.approx(0.6 * width, abs=1e-4)


def test_read_atd_rejects_non_contiguous_frame_ids(tmp_path):
    path = tmp_path / "gap_atd.txt"
    path.write_text(
        "1:0.1,0.2,1.0;0.5,0.5,NaN;NaN,NaN,NaN;0.9,0.1,0.0:0.3,0.4,2.0\n"
        "2:0.2,0.4,1.5;NaN,NaN,NaN;NaN,NaN,NaN;0.8,0.2,0.5:0.6,0.8,3.0\n"
        "4:0.3,0.6,2.0;NaN,NaN,NaN;NaN,NaN,NaN;NaN,NaN,NaN:NaN,NaN,NaN\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not contiguous"):
        read_atd(str(path), 4, DEFAULT)


def test_read_atd_rejects_a_line_with_the_wrong_number_of_separators(tmp_path):
    """A line is `frame:players:ball` — two separators, three fields."""
    path = tmp_path / "short_atd.txt"
    path.write_text("1:0.1,0.2,1.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected 3"):
        read_atd(str(path), 4, DEFAULT)


def test_read_atd_rejects_a_line_with_an_extra_separator(tmp_path):
    path = tmp_path / "long_atd.txt"
    path.write_text(
        "1:0.1,0.2,1.0;0.5,0.5,NaN;NaN,NaN,NaN;0.9,0.1,0.0:0.3,0.4,2.0:extra\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="expected 3"):
        read_atd(str(path), 4, DEFAULT)


def test_read_atd_rejects_a_line_with_the_wrong_number_of_slots(tmp_path):
    path = tmp_path / "slots_atd.txt"
    path.write_text(
        "1:0.1,0.2,1.0;0.5,0.5,NaN;NaN,NaN,NaN:0.3,0.4,2.0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="slots"):
        read_atd(str(path), 4, DEFAULT)


def test_read_atd_skips_blank_lines(tmp_path):
    path = tmp_path / "blank_atd.txt"
    path.write_text("\n" + RAW_LINES[0] + "\n\n" + RAW_LINES[1] + "\n", encoding="utf-8")
    arrays = read_atd(str(path), 4, DEFAULT)
    assert arrays["player_xy"].shape[0] == 2


# --------------------------------------------------------------------------------------------------
# parse_smart_tagging
# --------------------------------------------------------------------------------------------------


def test_parse_smart_tagging_reads_the_windows_in_seconds(tmp_path):
    path = tmp_path / "smart_tagging.xml"
    path.write_text(SMART_TAGGING_XML, encoding="utf-8")

    windows = parse_smart_tagging(str(path), fps=25.0)
    # The file groups the instances by code, not by time: the reader sorts them.
    assert windows == [
        (250, 1125, "Corner"),  # 10.0s .. 45.0s
        (1000, 1100, "Kick Off (Start)"),  # 40.0s .. 44.0s
    ]


def test_parse_smart_tagging_returns_nothing_when_the_file_is_absent(tmp_path):
    assert parse_smart_tagging(str(tmp_path / "missing.xml")) == []
