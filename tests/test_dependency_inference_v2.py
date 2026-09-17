from mouse_control.dependency_inference import DependencyKind, infer_dependencies


def test_nonuniform_values_distinguish_literal_scaled_duplicate_and_lookup() -> None:
    values = (800, 1300, 2400, 3100)
    frames = tuple(
        value.to_bytes(2, "little") + value.to_bytes(2, "little") +
        bytes((value // 100, index))
        for index, value in enumerate(values)
    )
    result = infer_dependencies(frames, values)
    assert any(c.kind is DependencyKind.LITERAL and c.offset == 0 for c in result.candidates)
    assert any(c.kind is DependencyKind.DUPLICATE and c.offset == 2 for c in result.candidates)
    assert any(c.kind is DependencyKind.SCALED and c.offset == 4 for c in result.candidates)
    assert any(c.kind is DependencyKind.LOOKUP and c.offset == 5 for c in result.candidates)


def test_unexplained_changing_bytes_block_promotion() -> None:
    frames = (b"\x20\x01", b"\x30\x09", b"\x40\x03")
    result = infer_dependencies(frames, (32, 48, 64))
    assert result.unexplained_offsets == (1,)
    assert not result.promotion_safe

