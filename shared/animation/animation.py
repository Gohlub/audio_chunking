"""
Sequence-merge overlap visualization (Manim one-off).

https://github.com/3b1b/manim
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from manim import (
    DL,
    DR,
    DOWN,
    FadeIn,
    FadeOut,
    GREEN,
    LEFT,
    Line,
    RED,
    ReplacementTransform,
    RIGHT,
    UP,
    WHITE,
    YELLOW,
    Rectangle,
    Scene,
    Text,
    VGroup,
    config,
)
from manim.utils.rate_functions import smooth

# Default render output next to this file (override with ``manim … --media_dir …``).
config.media_dir = str(Path(__file__).resolve().parent / "media")


def tokenize_words(seq: str) -> list[str]:
    return [w for w in re.split(r"(\s+\w+)", seq) if w]


def tokens_for(s: str, *, by_words: bool) -> list[str]:
    return tokenize_words(s) if by_words else list(s)


@dataclass(frozen=True)
class AlignmentStep:
    i: int
    left_start: int
    left_stop: int
    right_start: int
    right_stop: int
    matches: int
    score: float
    max_matching: float
    best_left_start: int
    best_left_stop: int
    best_right_start: int
    best_right_stop: int
    improved: bool


def collect_alignment_steps(
    left: list[str], right: list[str]
) -> tuple[list[AlignmentStep], tuple[int, int, int, int]]:
    """Record each scorable diagonal step (equal-length windows)."""
    left_length = len(left)
    right_length = len(right)
    max_matching = 0.0
    max_indices = (left_length, left_length, 0, 0)

    # First pass: final best indices for the pair.
    for i in range(1, left_length + right_length + 1):
        eps = float(i) / 10000.0
        ls = max(0, left_length - i)
        lstop = min(left_length, left_length + right_length - i)
        rs = max(0, i - left_length)
        rstop = min(right_length, i)
        if lstop - ls != rstop - rs:
            continue
        lw = left[ls:lstop]
        rw = right[rs:rstop]
        if len(lw) != len(rw):
            continue
        matches = sum(a == b for a, b in zip(lw, rw))
        score = matches / float(i) + eps
        if matches > 1 and score > max_matching:
            max_matching = score
            max_indices = (ls, lstop, rs, rstop)

    final_best = max_indices
    steps: list[AlignmentStep] = []
    max_matching = 0.0
    max_indices = (left_length, left_length, 0, 0)

    for i in range(1, left_length + right_length + 1):
        eps = float(i) / 10000.0
        left_start = max(0, left_length - i)
        left_stop = min(left_length, left_length + right_length - i)
        right_start = max(0, i - left_length)
        right_stop = min(right_length, i)
        if left_stop - left_start != right_stop - right_start:
            continue
        left_win = left[left_start:left_stop]
        right_win = right[right_start:right_stop]
        if len(left_win) != len(right_win):
            continue
        matches = sum(a == b for a, b in zip(left_win, right_win))
        score = matches / float(i) + eps
        improved = False
        if matches > 1 and score > max_matching:
            max_matching = score
            max_indices = (left_start, left_stop, right_start, right_stop)
            improved = True
        ls, lstop, rs, rstop = max_indices
        steps.append(
            AlignmentStep(
                i=i,
                left_start=left_start,
                left_stop=left_stop,
                right_start=right_start,
                right_stop=right_stop,
                matches=matches,
                score=score,
                max_matching=max_matching,
                best_left_start=ls,
                best_left_stop=lstop,
                best_right_start=rs,
                best_right_stop=rstop,
                improved=improved,
            )
        )

    return steps, final_best


class AnimationScene(Scene):
    def construct(self) -> None:
        self.camera.background_color = "#1a1a1e"
        rate = smooth
        S = 1.10

        def sci(x: float) -> int:
            return max(1, int(round(x * S)))

        left_raw = "send the final deck today"
        right_raw = "the final deck to Dave"
        left_tok = tokens_for(left_raw, by_words=True)
        right_tok = tokens_for(right_raw, by_words=True)
        steps, final_best = collect_alignment_steps(left_tok, right_tok)
    
        grey = "#888888"
        # Subtle straight match line: soft cyan, thin, low opacity
        link_stroke = "#8ed4f0"
    
        # Uniform sizing: pick font size from the longer row, then size every
        # box to the widest rendered token across both rows. Identical boxes
        # mean identical baselines — no per-cell scaling or vertical drift.
        n_max = max(len(left_tok), len(right_tok), 1)
        font_size = max(sci(18.0), sci(34.0) - n_max)
        cell_height = S * 0.85
        cell_pad = S * 0.18  # horizontal padding inside the box
        row_buff = S * 0.08

        def _display(tok: str) -> str:
            return tok.replace("\n", " ").strip() or tok.replace("\n", " ")

        # Render Text large then scale down (ManimCommunity/manim#2844).
        _up = 4

        def token_text(display: str) -> Text:
            t = Text(
                display,
                font_size=font_size * _up,
                color=WHITE,
                disable_ligatures=True,
            )
            t.scale(1.0 / _up)
            return t

        measure_texts = [token_text(_display(tok)) for tok in left_tok + right_tok]
        max_text_w = max((t.width for t in measure_texts), default=S * 0.4)
        cell_w = max(S * 0.7, min(max_text_w + 2 * cell_pad, S * 1.7))

        # Lower the rows once at layout time so two header lines fit above and
        # probe/best halos (copies of each cell rect) stay aligned — never shift
        # rows mid-scene after those copies are created.
        layout_drop = S * 0.20
        extra_row_separation = S * 0.22
        left_row_y = S * 1.35 - layout_drop
        right_row_y = S * (-0.1) - layout_drop - extra_row_separation
        row_x = S * (-1.45)

        def row(tokens: list[str], label: str, y: float) -> tuple[VGroup, Text]:
            cells: list[VGroup] = []
            inner_w = cell_w - 2 * cell_pad
            for j, tok in enumerate(tokens):
                t = token_text(_display(tok))
                box = Rectangle(width=cell_w, height=cell_height, stroke_color=grey, fill_opacity=0.12)
                # Safety net: if a token is unexpectedly wider than the
                # uniform cell (e.g. cell_w was clamped), shrink to fit.
                if t.width > inner_w:
                    t.scale(inner_w / t.width)
                t.move_to(box.get_center())
                idx_lab = Text(str(j), font_size=sci(16.0), color=grey)
                idx_lab.next_to(box, DOWN, buff=S * 0.08)
                g = VGroup(box, t, idx_lab)
                cells.append(g)
            row_g = VGroup(*cells).arrange(RIGHT, buff=row_buff).move_to([row_x, y, 0])
            cap = Text(label, font_size=sci(22.0), color=WHITE).next_to(row_g, LEFT, buff=S * 0.35)
            return row_g, cap

        left_row, left_cap = row(left_tok, "left", left_row_y)
        right_row, right_cap = row(right_tok, "right", right_row_y)

        def scan_slice(name: str, start: int, stop: int) -> str:
            return f"{name}[{start}:{stop}]"

        candidate_steps = [
            st for st in steps if st.left_stop > st.left_start and st.matches > 0
        ]
        col_gap = S * 0.30
        table_row_buff = S * 0.13
        hfs = sci(27.0)
        bfs = sci(25.0)
        body_color = "#8e8e9a"

        header_strs = ("left", "right", "overlap")
        data_strs: list[tuple[str, str, str]] = [
            (
                scan_slice("L", st.left_start, st.left_stop),
                scan_slice("R", st.right_start, st.right_stop),
                str(st.matches),
            )
            for st in candidate_steps
        ]

        def _cell(s: str, *, fs: int, color: str) -> Text:
            t = Text(s, font_size=int(fs * _up), color=color, disable_ligatures=True)
            t.scale(1.0 / _up)
            return t

        col_max = [0.0, 0.0, 0.0]
        for j in range(3):
            w_header = _cell(header_strs[j], fs=hfs, color=grey).width
            w_data = max(
                (_cell(triple[j], fs=bfs, color=body_color).width for triple in data_strs),
                default=0.0,
            )
            col_max[j] = max(w_header, w_data)

        def _layout_row(triple: tuple[str, str, str], *, fs: int, color: str) -> VGroup:
            parts = [_cell(s, fs=fs, color=color) for s in triple]
            x = 0.0
            for j, p in enumerate(parts):
                p.move_to([x + col_max[j] / 2.0, 0.0, 0.0])
                x += col_max[j] + col_gap
            return VGroup(*parts)

        table_header = _layout_row(header_strs, fs=hfs, color=grey)
        table_entries: list[VGroup] = [_layout_row(triple, fs=bfs, color=body_color) for triple in data_strs]

        rule_left = table_header.get_corner(DL) + LEFT * (S * 0.02)
        rule_right = table_header.get_corner(DR) + RIGHT * (S * 0.02)
        header_rule = Line(
            rule_left + DOWN * (S * 0.04),
            rule_right + DOWN * (S * 0.04),
            stroke_color=grey,
            stroke_width=S * 1.0,
            stroke_opacity=0.22,
        )
        prev = VGroup(table_header, header_rule)
        for entry in table_entries:
            entry.next_to(prev, DOWN, aligned_edge=LEFT, buff=table_row_buff)
            prev = entry

        table_group = VGroup(table_header, header_rule, *table_entries)
        table_group.to_edge(RIGHT, buff=S * 1.0).shift(UP * (S * 2.0))
        # Horizontal center: midpoint between the rows’ right edge and the frame’s right edge
        # (equal empty space on both sides of the table). Vertical unchanged from ``to_edge`` + ``shift``.
        frame_right = float(config.frame_width) / 2.0
        content_right = max(
            left_row.get_right()[0],
            right_row.get_right()[0],
        )
        cy = float(table_group.get_center()[1])
        table_center_x = (content_right + frame_right) / 2.0
        table_group.move_to([table_center_x, cy, 0.0])
    
        self.add(
            left_cap,
            left_row,
            right_cap,
            right_row,
            table_header,
            header_rule,
        )
        self.wait(S * 1.7)
    
        probe_left: list[Rectangle] = []
        probe_right: list[Rectangle] = []
        best_left: list[Rectangle] = []
        best_right: list[Rectangle] = []
        match_lines: list[Any] = []
    
        def clear_moblists(mobs: list[Any]) -> None:
            for m in mobs:
                self.remove(m)
            mobs.clear()
    
        rt = S * 0.38
        visible_table_rows: list[VGroup] = []
        for st in steps:
            clear_moblists(probe_left)
            clear_moblists(probe_right)
            clear_moblists(best_left)
            clear_moblists(best_right)
            clear_moblists(match_lines)
    
            # Running best outline: softer yellow (thinner, lower opacity)
            # so it sits *under* the bright probe but still marks the
            # current winning overlap. The yellow probe already conveys
            # "this subsequence has matches"; no extra color needed.
            # Naturally invisible while the sentinel best is still empty.
            for j in range(st.best_left_start, st.best_left_stop):
                r = left_row[j][0].copy()
                r.set_stroke(YELLOW, width=S * 3.0, opacity=0.6)
                self.add(r)
                best_left.append(r)
            for j in range(st.best_right_start, st.best_right_stop):
                r = right_row[j][0].copy()
                r.set_stroke(YELLOW, width=S * 3.0, opacity=0.6)
                self.add(r)
                best_right.append(r)

            # Current probe: bright yellow border on the window being scored.
            for j in range(st.left_start, st.left_stop):
                r = left_row[j][0].copy()
                r.set_stroke(YELLOW, width=S * 5.0)
                self.add(r)
                probe_left.append(r)
            for j in range(st.right_start, st.right_stop):
                r = right_row[j][0].copy()
                r.set_stroke(YELLOW, width=S * 5.0)
                self.add(r)
                probe_right.append(r)
    
            # Match connectors: thin soft straight lines (subtle)
            if st.left_stop - st.left_start == st.right_stop - st.right_start and st.left_stop > st.left_start:
                for a, b in zip(
                    range(st.left_start, st.left_stop),
                    range(st.right_start, st.right_stop),
                ):
                    if left_tok[a] == right_tok[b]:
                        p0 = left_row[a].get_bottom() + (S * 0.06) * DOWN
                        p1 = right_row[b].get_top() + (S * 0.06) * UP
                        ln = Line(
                            p0,
                            p1,
                            stroke_color=link_stroke,
                            stroke_width=S * 1.6,
                            stroke_opacity=0.55,
                        )
                        self.add(ln)
                        match_lines.append(ln)
    
            if st.left_stop > st.left_start and st.matches > 0:
                row_idx = len(visible_table_rows)
                if row_idx < len(table_entries):
                    entry = table_entries[row_idx]
                    visible_table_rows.append(entry)
                    self.play(
                        FadeIn(entry, shift=LEFT * (S * 0.08)),
                        run_time=min(S * 0.18, rt * 0.5),
                        rate_func=rate,
                    )
                    self.wait(max(0.0, rt - min(S * 0.18, rt * 0.5)))
                else:
                    self.wait(rt)
            else:
                self.wait(rt)
    
        # Settle on the winning overlap. The (softer) yellow halos from
        # the last iteration step still mark the best subsequence; clear
        # only the transient probe and match lines.
        clear_moblists(probe_left)
        clear_moblists(probe_right)
        clear_moblists(match_lines)

        ls, lstop, rs, rstop = final_best
        left_mid = (lstop + ls) // 2
        right_mid = (rstop + rs) // 2
        winning_table_row = next(
            (
                row
                for st, row in zip(candidate_steps, table_entries)
                if (
                    st.left_start,
                    st.left_stop,
                    st.right_start,
                    st.right_stop,
                )
                == final_best
            ),
            None,
        )
        if winning_table_row is not None:
            self.play(
                *[
                    t.animate.set_color(YELLOW).set_opacity(1.0)
                    for t in winning_table_row
                ],
                run_time=S * 0.35,
                rate_func=rate,
            )
            self.wait(S * 0.25)

        # Slide rows + halos to center while the table morphs into the merge line (one play).
        center_targets: list[Any] = [
            left_cap,
            left_row,
            right_cap,
            right_row,
            table_group,
            *best_left,
            *best_right,
        ]
        cx = sum(m.get_center()[0] for m in center_targets) / len(center_targets)
        cy = sum(m.get_center()[1] for m in center_targets) / len(center_targets)
        goal_x, goal_y = 0.0, S * 0.32
        focus_shift = RIGHT * (goal_x - cx) + UP * (goal_y - cy)
        shift_y = float(focus_shift[1])

        merge_fs = sci(30.0)
        merge_label = _cell(
            f"left = left[:{left_mid}] + right[{right_mid}:]",
            fs=merge_fs,
            color=body_color,
        )
        top_y = max(
            left_cap.get_top()[1] + shift_y,
            right_cap.get_top()[1] + shift_y,
            left_row.get_top()[1] + shift_y,
            right_row.get_top()[1] + shift_y,
            table_group.get_top()[1] + shift_y,
        )
        merge_label.move_to(
            [
                0.0,
                float(top_y) + S * 0.05 + float(merge_label.height) / 2.0,
                0.0,
            ]
        )

        slide_targets: list[Any] = [
            left_cap,
            left_row,
            right_cap,
            right_row,
            *best_left,
            *best_right,
        ]
        self.play(
            *[m.animate.shift(focus_shift) for m in slide_targets],
            ReplacementTransform(
                table_group,
                merge_label,
                path_arc=-0.22,
            ),
            run_time=S * 0.78,
            rate_func=rate,
        )
        # Transition from yellow (best overlap) to green/red (kept/dropped).
        recolor_anims: list[Any] = []
        for j in range(len(left_tok)):
            color = GREEN if j < left_mid else RED
            recolor_anims.append(left_row[j][0].animate.set_stroke(color, width=S * 4.0))
        for j in range(len(right_tok)):
            color = RED if j < right_mid else GREEN
            recolor_anims.append(right_row[j][0].animate.set_stroke(color, width=S * 4.0))

        self.play(
            *[FadeOut(h) for h in best_left + best_right],
            *recolor_anims,
            run_time=S * 0.55,
            rate_func=rate,
        )
        best_left.clear()
        best_right.clear()
        self.wait(S * 0.55)
    
        # Build the merged strip by reusing the surviving cells: head from the
        # left row, tail from the right row; slide both into a single row.
        left_head_idx = list(range(0, left_mid))
        right_tail_idx = list(range(right_mid, len(right_tok)))
        n_keep_left = len(left_head_idx)
        n_keep_right = len(right_tail_idx)
        n_total = n_keep_left + n_keep_right
    
        # Identify everything that should disappear before/while we merge:
        # the red (dropped) cells from each row, row labels/indices, and any
        # leftover match lines. The green (kept) cells slide into the merged row.
        discard_mobs: list[Any] = []
        for j, cell in enumerate(left_row):
            if j not in left_head_idx:
                discard_mobs.append(cell)
        for j, cell in enumerate(right_row):
            if j not in right_tail_idx:
                discard_mobs.append(cell)
        for j in left_head_idx:
            discard_mobs.append(left_row[j][2])
        for j in right_tail_idx:
            discard_mobs.append(right_row[j][2])
        discard_mobs.extend([left_cap, right_cap])
        discard_mobs.extend(match_lines)

        # Slide kept cells into a single centered row using the uniform cell_w.
        buff = S * 0.18
        stride = cell_w + buff
        x0 = -((n_total - 1) / 2.0) * stride
        final_positions = [[x0 + k * stride, 0.0, 0.0] for k in range(n_total)]

        # Preserve (text - box) offset while sliding so glyph-based centering
        # from ``optical_center_text_in_box`` is not erased.
        slide_anims: list[Any] = []
        for k, j in enumerate(left_head_idx):
            cell = left_row[j]
            box_m, txt_m = cell[0], cell[1]
            fx, fy, fz = final_positions[k]
            dc = txt_m.get_center() - box_m.get_center()
            slide_anims.append(box_m.animate.move_to([fx, fy, fz]))
            slide_anims.append(
                txt_m.animate.move_to([fx + float(dc[0]), fy + float(dc[1]), fz + float(dc[2])])
            )
        for k, j in enumerate(right_tail_idx):
            cell = right_row[j]
            box_m, txt_m = cell[0], cell[1]
            fx, fy, fz = final_positions[n_keep_left + k]
            dc = txt_m.get_center() - box_m.get_center()
            slide_anims.append(box_m.animate.move_to([fx, fy, fz]))
            slide_anims.append(
                txt_m.animate.move_to([fx + float(dc[0]), fy + float(dc[1]), fz + float(dc[2])])
            )

        self.play(
            FadeOut(merge_label, shift=UP * (S * 0.12)),
            *[FadeOut(m) for m in discard_mobs],
            run_time=S * 0.45,
            rate_func=rate,
        )
        best_left.clear()
        best_right.clear()
        match_lines.clear()

        # Old row indices (under kept cells) are gone visually; drop them from
        # the cell groups so the slide only moves box + token.
        for j in left_head_idx:
            c = left_row[j]
            if len(c) > 2:
                dead = c[2]
                c.remove(dead)
                self.remove(dead)
        for j in right_tail_idx:
            c = right_row[j]
            if len(c) > 2:
                dead = c[2]
                c.remove(dead)
                self.remove(dead)

        self.play(*slide_anims, run_time=S * 1.55, rate_func=rate)

        merged_strip = VGroup()
        for j in left_head_idx:
            merged_strip.add(left_row[j])
        for j in right_tail_idx:
            merged_strip.add(right_row[j])
        merged_left_cap = Text("left", font_size=sci(22.0), color=WHITE, disable_ligatures=True)
        merged_left_cap.next_to(merged_strip, LEFT, buff=S * 0.35)
        merged_idx_anims: list[Any] = []
        for k in range(n_total):
            cell = merged_strip[k]
            lab = Text(str(k), font_size=sci(16.0), color=grey)
            lab.next_to(cell[0], DOWN, buff=S * 0.08)
            cell.add(lab)
            merged_idx_anims.append(FadeIn(lab, shift=DOWN * (S * 0.06)))
        self.play(
            FadeIn(merged_left_cap, shift=RIGHT * (S * 0.12)),
            *merged_idx_anims,
            run_time=S * 0.4,
            rate_func=rate,
        )
        self.wait(S * 0.55)
