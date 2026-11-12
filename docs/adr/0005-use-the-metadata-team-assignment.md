# The metadata's slot-to-team assignment is used as it stands

The organisers warn that track slots swap identity as the tracker loses and re-acquires people,
and at least one high-usage slot does contradict the metadata for part of the match. We tried to
repair the mapping from the data — assigning each slot the team of the majority of its nearest
spatial neighbours — and it failed: the two teams interleave spatially, so neighbour voting
recovers a left/right partition of the pitch rather than two teams, and it flips at half time when
the teams change ends. It changed 13 % of slot-frames and inverted our possession share, so the
experiment lives in `mtah/teams.py` switched off, with the reason recorded.
