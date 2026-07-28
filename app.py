from __future__ import annotations

import json
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
import re
from string import ascii_uppercase

import pandas as pd
import streamlit as st

try:
    import nltk
except ImportError:
    nltk = None

NLTK_CORPUS_OPTIONS = {
    "Brown": "brown",
    "Gutenberg": "gutenberg",
    "Reuters": "reuters",
    "Inaugural": "inaugural",
    "State of the Union": "state_union",
    "Webtext": "webtext",
}

UPLOAD_PLAIN_TEXT_OPTION = "Upload plain text"

ALPHABET_ASCENDING = list(ascii_uppercase)

THEME_PRESETS = {
    "Paper & Ink": {
        "app_bg": "#f6f1e7",
        "app_fg": "#2e2a24",
        "panel_bg": "#fffaf1",
        "panel_border": "#d6cbb8",
        "display_bg": "#fffcf7",
        "display_border": "#ddd1be",
        "sub_color": "#1f252f",
        "unsolved_color": "#6d6357",
        "button_bg": "#efe3d2",
        "button_fg": "#2e2a24",
        "button_border": "#bfae95",
    },
    "Nord Cipher": {
        "app_bg": "#2e3440",
        "app_fg": "#eceff4",
        "panel_bg": "#3b4252",
        "panel_border": "#4c566a",
        "display_bg": "#434c5e",
        "display_border": "#5e81ac",
        "sub_color": "#88c0d0",
        "unsolved_color": "#d8dee9",
        "button_bg": "#4c566a",
        "button_fg": "#eceff4",
        "button_border": "#81a1c1",
    },
}

COMMON_BIGRAMS = {
    "TH",
    "HE",
    "IN",
    "ER",
    "AN",
    "RE",
    "ON",
    "AT",
    "EN",
    "ND",
    "TI",
    "ES",
    "OR",
    "TE",
    "OF",
    "ED",
    "IS",
    "IT",
    "AL",
    "AR",
    "ST",
    "TO",
    "NT",
    "NG",
    "SE",
    "HA",
    "AS",
    "OU",
    "IO",
    "LE",
    "VE",
    "CO",
    "ME",
    "DE",
    "HI",
    "RI",
    "RO",
    "IC",
    "NE",
    "EA",
}

COMMON_TRIGRAMS = {
    "THE",
    "AND",
    "ING",
    "HER",
    "ERE",
    "ENT",
    "THA",
    "NTH",
    "WAS",
    "ETH",
    "FOR",
    "DTH",
    "HAT",
    "ION",
    "TIO",
    "VER",
    "TER",
    "HES",
    "ALL",
    "HIS",
    "OFT",
    "ITH",
    "FTH",
    "STH",
    "OTH",
}

PATTERN_CANDIDATE_LIMIT = 6
PATTERN_FAST_MAX_SCAN_PER_BUCKET = 300
PATTERN_MAX_ROWS = 20


def initialize_state() -> None:
    if "defaults_seeded" not in st.session_state:
        st.session_state.defaults_seeded = False

    if "cryptogram_text" not in st.session_state:
        st.session_state.cryptogram_text = ""

    if "uploaded_filename" not in st.session_state:
        st.session_state.uploaded_filename = ""

    if "uploader_version" not in st.session_state:
        st.session_state.uploader_version = 0

    if "cryptogram_input_mode" not in st.session_state:
        st.session_state.cryptogram_input_mode = "Use default sample"

    if "active_cryptogram_source" not in st.session_state:
        st.session_state.active_cryptogram_source = "default"

    if "corpus_source_selection" not in st.session_state:
        st.session_state.corpus_source_selection = "NLTK Corpus Brown (default)"

    if "data_sheet_selection" not in st.session_state:
        st.session_state.data_sheet_selection = "None"

    if "visual_theme" not in st.session_state:
        st.session_state.visual_theme = "Paper & Ink"

    if "substitutions" not in st.session_state:
        st.session_state.substitutions = {letter: "" for letter in ALPHABET_ASCENDING}

    if "likely_chars" not in st.session_state:
        st.session_state.likely_chars = {letter: "" for letter in ALPHABET_ASCENDING}

    if "rejected_chars" not in st.session_state:
        st.session_state.rejected_chars = {letter: "" for letter in ALPHABET_ASCENDING}

    if "locked_letters" not in st.session_state:
        st.session_state.locked_letters = {letter: False for letter in ALPHABET_ASCENDING}

    if "mapping_history" not in st.session_state:
        st.session_state.mapping_history = []

    if "mapping_history_index" not in st.session_state:
        st.session_state.mapping_history_index = -1

    if "suppress_history" not in st.session_state:
        st.session_state.suppress_history = False

    if "import_payload_text" not in st.session_state:
        st.session_state.import_payload_text = ""

    if "pattern_scan_mode" not in st.session_state:
        st.session_state.pattern_scan_mode = "Full scan"

    if "pending_session_import_payload" not in st.session_state:
        st.session_state.pending_session_import_payload = None

    if "session_import_notice" not in st.session_state:
        st.session_state.session_import_notice = False

    for letter in ALPHABET_ASCENDING:
        sub_key = f"sub_{letter}"
        likely_key = f"likely_{letter}"
        rejected_key = f"rejected_{letter}"
        lock_key = f"lock_{letter}"

        if sub_key not in st.session_state:
            st.session_state[sub_key] = st.session_state.substitutions[letter]

        if likely_key not in st.session_state:
            st.session_state[likely_key] = st.session_state.likely_chars[letter]

        if rejected_key not in st.session_state:
            st.session_state[rejected_key] = st.session_state.rejected_chars[letter]

        if lock_key not in st.session_state:
            st.session_state[lock_key] = st.session_state.locked_letters[letter]


def seed_defaults_on_first_load() -> None:
    if st.session_state.defaults_seeded:
        return

    default_cryptogram_path = Path(__file__).resolve().parent / "data" / "illustrative_problem_2.txt"
    if default_cryptogram_path.exists() and not st.session_state.cryptogram_text:
        default_text = default_cryptogram_path.read_text(encoding="utf-8", errors="replace")
        st.session_state.cryptogram_text = default_text.replace("\r\n", "\n")
        st.session_state.uploaded_filename = default_cryptogram_path.name

    st.session_state.cryptogram_input_mode = "Use default sample"
    st.session_state.active_cryptogram_source = "default"
    st.session_state.corpus_source_selection = "NLTK Corpus Brown (default)"
    st.session_state.data_sheet_selection = "None"
    st.session_state.defaults_seeded = True


def get_default_cryptogram_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "illustrative_problem_2.txt"


def load_default_cryptogram() -> None:
    default_path = get_default_cryptogram_path()
    if not default_path.exists():
        st.warning("Default sample file is missing: data/illustrative_problem_2.txt")
        return

    default_text = default_path.read_text(encoding="utf-8", errors="replace")
    st.session_state.cryptogram_text = default_text.replace("\r\n", "\n")
    st.session_state.uploaded_filename = default_path.name
    st.session_state.active_cryptogram_source = "default"


def normalize_single_letter(value: str) -> str:
    letters_only = "".join(character for character in value.upper() if character in ascii_uppercase)
    return letters_only[:1]


def normalize_multi_entry(value: str) -> str:
    return "".join(character for character in value.upper() if character in ascii_uppercase)


def mapping_snapshot() -> dict[str, dict[str, str] | dict[str, bool]]:
    return {
        "substitutions": dict(st.session_state.substitutions),
        "likely_chars": dict(st.session_state.likely_chars),
        "rejected_chars": dict(st.session_state.rejected_chars),
        "locked_letters": dict(st.session_state.locked_letters),
    }


def apply_mapping_snapshot(snapshot: dict[str, dict[str, str] | dict[str, bool]]) -> None:
    st.session_state.suppress_history = True

    substitutions = snapshot.get("substitutions", {})
    likely_chars = snapshot.get("likely_chars", {})
    rejected_chars = snapshot.get("rejected_chars", {})
    locked_letters = snapshot.get("locked_letters", {})

    for letter in ALPHABET_ASCENDING:
        substitution = normalize_single_letter(str(substitutions.get(letter, "")))
        likely = normalize_multi_entry(str(likely_chars.get(letter, "")))
        rejected = normalize_multi_entry(str(rejected_chars.get(letter, "")))
        locked = bool(locked_letters.get(letter, False))

        st.session_state.substitutions[letter] = substitution
        st.session_state.likely_chars[letter] = likely
        st.session_state.rejected_chars[letter] = rejected
        st.session_state.locked_letters[letter] = locked

        st.session_state[f"sub_{letter}"] = substitution
        st.session_state[f"likely_{letter}"] = likely
        st.session_state[f"rejected_{letter}"] = rejected
        st.session_state[f"lock_{letter}"] = locked

    st.session_state.suppress_history = False


def initialize_mapping_history() -> None:
    if st.session_state.mapping_history:
        return

    st.session_state.mapping_history = [mapping_snapshot()]
    st.session_state.mapping_history_index = 0


def push_history_snapshot() -> None:
    if st.session_state.suppress_history:
        return

    current_snapshot = mapping_snapshot()
    history = st.session_state.mapping_history
    history_index = st.session_state.mapping_history_index

    if history_index >= 0 and history and history[history_index] == current_snapshot:
        return

    if history_index < len(history) - 1:
        history = history[: history_index + 1]

    history.append(current_snapshot)

    if len(history) > 200:
        history = history[-200:]

    st.session_state.mapping_history = history
    st.session_state.mapping_history_index = len(history) - 1


def undo_mapping_change() -> None:
    if st.session_state.mapping_history_index <= 0:
        return

    st.session_state.mapping_history_index -= 1
    snapshot = st.session_state.mapping_history[st.session_state.mapping_history_index]
    apply_mapping_snapshot(snapshot)


def redo_mapping_change() -> None:
    if st.session_state.mapping_history_index >= len(st.session_state.mapping_history) - 1:
        return

    st.session_state.mapping_history_index += 1
    snapshot = st.session_state.mapping_history[st.session_state.mapping_history_index]
    apply_mapping_snapshot(snapshot)


def update_letter_field(letter: str, field_name: str, normalized_value: str) -> None:
    if st.session_state.locked_letters[letter]:
        current_value = st.session_state[field_name][letter]
        if field_name == "substitutions":
            st.session_state[f"sub_{letter}"] = current_value
        elif field_name == "likely_chars":
            st.session_state[f"likely_{letter}"] = current_value
        else:
            st.session_state[f"rejected_{letter}"] = current_value
        return

    current_value = st.session_state[field_name][letter]
    if normalized_value == current_value:
        return

    st.session_state[field_name][letter] = normalized_value
    push_history_snapshot()


def on_lock_change(letter: str) -> None:
    lock_key = f"lock_{letter}"
    new_value = bool(st.session_state.get(lock_key, False))

    if st.session_state.locked_letters[letter] == new_value:
        return

    st.session_state.locked_letters[letter] = new_value
    push_history_snapshot()


def compute_substitution_conflicts(substitutions: dict[str, str]) -> dict[str, list[str]]:
    substitution_to_letters: dict[str, list[str]] = defaultdict(list)
    for letter, mapped_value in substitutions.items():
        if mapped_value:
            substitution_to_letters[mapped_value].append(letter)

    conflicts: dict[str, list[str]] = {}
    for letters in substitution_to_letters.values():
        if len(letters) > 1:
            for letter in letters:
                conflicts[letter] = letters

    return conflicts


def compute_self_substitutions(substitutions: dict[str, str]) -> set[str]:
    return {
        letter
        for letter, mapped_value in substitutions.items()
        if mapped_value and mapped_value == letter
    }


def build_plaintext_preview(cryptogram_text: str, substitutions: dict[str, str], unknown_character: str = "_") -> str:
    preview_characters: list[str] = []
    for character in cryptogram_text:
        upper = character.upper()
        if upper in substitutions:
            mapped = substitutions[upper]
            preview_characters.append(mapped if mapped else unknown_character)
        else:
            preview_characters.append(character)
    return "".join(preview_characters)


def build_word_shape_signature(word: str) -> str:
    seen: dict[str, str] = {}
    next_id = 0
    encoded_parts: list[str] = []

    for character in word.upper():
        if character not in seen:
            seen[character] = chr(ord("A") + next_id)
            next_id += 1
        encoded_parts.append(seen[character])

    return "".join(encoded_parts)


def has_repeated_shape_letters(shape_signature: str) -> bool:
    return len(set(shape_signature)) < len(shape_signature)


@st.cache_data(show_spinner=False)
def build_corpus_pattern_index(corpus_text: str) -> tuple[dict[str, list[tuple[str, int]]], dict[str, int]]:
    words = re.findall(r"[A-Za-z]+", corpus_text)
    word_counter = Counter(word.lower() for word in words)

    grouped: dict[str, list[tuple[str, int]]] = defaultdict(list)
    indexed_word_count = 0
    for word, count in word_counter.items():
        shape_signature = build_word_shape_signature(word)
        if not has_repeated_shape_letters(shape_signature):
            continue

        key = f"{len(word)}|{shape_signature}"
        grouped[key].append((word, count))
        indexed_word_count += 1

    for key in grouped:
        grouped[key].sort(key=lambda item: item[1], reverse=True)

    largest_bucket = max((len(bucket) for bucket in grouped.values()), default=0)
    index_metrics = {
        "tokens": len(words),
        "unique_words": len(word_counter),
        "indexed_words": indexed_word_count,
        "shape_buckets": len(grouped),
        "largest_bucket": largest_bucket,
    }

    return dict(grouped), index_metrics


def resolve_pattern_candidates(
    cipher_word: str,
    substitutions: dict[str, str],
    pattern_index: dict[str, list[tuple[str, int]]],
    candidate_limit: int = PATTERN_CANDIDATE_LIMIT,
    max_bucket_scan: int | None = None,
) -> tuple[list[str], int, int]:
    key = f"{len(cipher_word)}|{build_word_shape_signature(cipher_word)}"
    candidates = pattern_index.get(key, [])
    bucket_size = len(candidates)
    scan_limit = bucket_size if max_bucket_scan is None else min(bucket_size, max_bucket_scan)

    filtered_candidates: list[str] = []
    scanned_count = 0
    for candidate_word, _count in candidates[:scan_limit]:
        scanned_count += 1
        candidate_upper = candidate_word.upper()
        matches_known_letters = True
        for index, cipher_character in enumerate(cipher_word.upper()):
            mapped = substitutions.get(cipher_character, "")
            if mapped and candidate_upper[index] != mapped:
                matches_known_letters = False
                break

        if matches_known_letters:
            filtered_candidates.append(candidate_word)

        if len(filtered_candidates) >= candidate_limit:
            break

    return filtered_candidates, scanned_count, bucket_size


def sanitize_mapping_dict(raw_value: object, single_character: bool) -> dict[str, str]:
    sanitized = {letter: "" for letter in ALPHABET_ASCENDING}
    if not isinstance(raw_value, dict):
        return sanitized

    for letter in ALPHABET_ASCENDING:
        value = str(raw_value.get(letter, ""))
        sanitized[letter] = normalize_single_letter(value) if single_character else normalize_multi_entry(value)

    return sanitized


def sanitize_locked_dict(raw_value: object) -> dict[str, bool]:
    sanitized = {letter: False for letter in ALPHABET_ASCENDING}
    if not isinstance(raw_value, dict):
        return sanitized

    for letter in ALPHABET_ASCENDING:
        sanitized[letter] = bool(raw_value.get(letter, False))

    return sanitized


def export_session_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "cryptogram_text": st.session_state.cryptogram_text,
        "uploaded_filename": st.session_state.uploaded_filename,
        "active_cryptogram_source": st.session_state.active_cryptogram_source,
        "cryptogram_input_mode": st.session_state.cryptogram_input_mode,
        "corpus_source_selection": st.session_state.corpus_source_selection,
        "data_sheet_selection": st.session_state.data_sheet_selection,
        "visual_theme": st.session_state.visual_theme,
        "substitutions": dict(st.session_state.substitutions),
        "likely_chars": dict(st.session_state.likely_chars),
        "rejected_chars": dict(st.session_state.rejected_chars),
        "locked_letters": dict(st.session_state.locked_letters),
    }


def import_session_payload(payload: dict[str, object]) -> None:
    st.session_state.suppress_history = True

    st.session_state.cryptogram_text = str(payload.get("cryptogram_text", ""))
    st.session_state.uploaded_filename = str(payload.get("uploaded_filename", ""))
    st.session_state.active_cryptogram_source = str(payload.get("active_cryptogram_source", "upload"))
    st.session_state.cryptogram_input_mode = str(payload.get("cryptogram_input_mode", "Upload file"))
    st.session_state.corpus_source_selection = str(
        payload.get("corpus_source_selection", "NLTK Corpus Brown (default)")
    )
    st.session_state.data_sheet_selection = str(payload.get("data_sheet_selection", "None"))
    st.session_state.visual_theme = str(payload.get("visual_theme", "Paper & Ink"))

    st.session_state.substitutions = sanitize_mapping_dict(payload.get("substitutions"), single_character=True)
    st.session_state.likely_chars = sanitize_mapping_dict(payload.get("likely_chars"), single_character=False)
    st.session_state.rejected_chars = sanitize_mapping_dict(payload.get("rejected_chars"), single_character=False)
    st.session_state.locked_letters = sanitize_locked_dict(payload.get("locked_letters"))

    for letter in ALPHABET_ASCENDING:
        st.session_state[f"sub_{letter}"] = st.session_state.substitutions[letter]
        st.session_state[f"likely_{letter}"] = st.session_state.likely_chars[letter]
        st.session_state[f"rejected_{letter}"] = st.session_state.rejected_chars[letter]
        st.session_state[f"lock_{letter}"] = st.session_state.locked_letters[letter]

    st.session_state.mapping_history = [mapping_snapshot()]
    st.session_state.mapping_history_index = 0
    st.session_state.suppress_history = False


def apply_pending_session_import() -> None:
    pending_payload = st.session_state.get("pending_session_import_payload")
    if not isinstance(pending_payload, dict):
        return

    import_session_payload(pending_payload)
    st.session_state.pending_session_import_payload = None
    st.session_state.session_import_notice = True


def on_substitution_change(letter: str) -> None:
    sub_key = f"sub_{letter}"
    raw_value = st.session_state.get(sub_key, "")
    normalized_value = normalize_single_letter(raw_value)

    if raw_value != normalized_value:
        st.session_state[sub_key] = normalized_value

    update_letter_field(letter, "substitutions", normalized_value)


def on_likely_change(letter: str) -> None:
    likely_key = f"likely_{letter}"
    raw_value = st.session_state.get(likely_key, "")
    normalized_value = normalize_multi_entry(raw_value)

    if raw_value != normalized_value:
        st.session_state[likely_key] = normalized_value

    update_letter_field(letter, "likely_chars", normalized_value)


def on_rejected_change(letter: str) -> None:
    rejected_key = f"rejected_{letter}"
    raw_value = st.session_state.get(rejected_key, "")
    normalized_value = normalize_multi_entry(raw_value)

    if raw_value != normalized_value:
        st.session_state[rejected_key] = normalized_value

    update_letter_field(letter, "rejected_chars", normalized_value)


def reset_mappings() -> None:
    for letter in ALPHABET_ASCENDING:
        if st.session_state.locked_letters[letter]:
            continue
        st.session_state.substitutions[letter] = ""
        st.session_state.likely_chars[letter] = ""
        st.session_state.rejected_chars[letter] = ""
        st.session_state[f"sub_{letter}"] = ""
        st.session_state[f"likely_{letter}"] = ""
        st.session_state[f"rejected_{letter}"] = ""

    push_history_snapshot()


def reset_all() -> None:
    reset_mappings()
    st.session_state.suppress_history = True
    for letter in ALPHABET_ASCENDING:
        st.session_state.locked_letters[letter] = False
        st.session_state[f"lock_{letter}"] = False
    st.session_state.suppress_history = False

    st.session_state.active_cryptogram_source = ""
    st.session_state.uploader_version += 1
    load_default_cryptogram()
    st.session_state.mapping_history = [mapping_snapshot()]
    st.session_state.mapping_history_index = 0

def load_uploaded_text() -> None:
    st.markdown("**Cryptogram input**")
    input_mode = st.segmented_control(
        "Source",
        options=["Use default sample", "Upload file"],
        key="cryptogram_input_mode",
    )

    if input_mode == "Use default sample":
        if st.session_state.active_cryptogram_source != "default":
            load_default_cryptogram()
        st.caption(f"Active cryptogram: {st.session_state.uploaded_filename}")
        return

    uploaded_file = st.file_uploader(
        "Upload cryptogram (.txt)",
        type=["txt"],
        key=f"cryptogram_uploader_{st.session_state.uploader_version}",
    )

    if uploaded_file is None:
        st.caption("Upload a .txt file to use a custom cryptogram.")
        return

    if uploaded_file.name != st.session_state.uploaded_filename or st.session_state.active_cryptogram_source != "upload":
        decoded_text = uploaded_file.getvalue().decode("utf-8", errors="replace")
        st.session_state.cryptogram_text = decoded_text.replace("\r\n", "\n")
        st.session_state.uploaded_filename = uploaded_file.name
        st.session_state.active_cryptogram_source = "upload"

    st.caption(f"Active cryptogram: {st.session_state.uploaded_filename}")


def render_original_cryptogram() -> None:
    st.subheader("Original cryptogram", anchor=False)

    if not st.session_state.cryptogram_text:
        st.caption("Load a .txt cryptogram file to begin.")
        return

    st.text(st.session_state.cryptogram_text)


def build_substitution_html(cryptogram_text: str, substitutions: dict[str, str]) -> str:
    rendered_segments: list[str] = []

    for character in cryptogram_text:
        upper = character.upper()

        if upper in substitutions:
            mapped_value = substitutions[upper]
            if mapped_value:
                rendered_segments.append(
                    f"<span class='sub-letter'>{escape(mapped_value.upper())}</span>"
                )
            else:
                rendered_segments.append(f"<span class='unsolved-letter'>{escape(upper.lower())}</span>")
        else:
            rendered_segments.append(escape(character))

    return "".join(rendered_segments)


def render_substitution_cryptogram() -> None:
    st.subheader("Substitution view", anchor=False)

    if not st.session_state.cryptogram_text:
        st.caption("Substitutions will appear here.")
        return

    html = build_substitution_html(st.session_state.cryptogram_text, st.session_state.substitutions)

    st.markdown(
        f"""
        <div class="cryptogram-display">{html}</div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def load_nltk_corpus_text(corpus_resource_name: str) -> str:
    if nltk is None:
        raise RuntimeError("NLTK is not installed. Install `nltk` to use the Brown corpus.")

    try:
        corpus_reader = getattr(nltk.corpus, corpus_resource_name)
        words = corpus_reader.words()
    except LookupError:
        downloaded = nltk.download(corpus_resource_name, quiet=True)
        if not downloaded:
            raise RuntimeError(f"Unable to download the NLTK corpus '{corpus_resource_name}'.")
        corpus_reader = getattr(nltk.corpus, corpus_resource_name)
        words = corpus_reader.words()
    except Exception as error:
        raise RuntimeError(f"Unable to load the NLTK corpus '{corpus_resource_name}': {error}") from error

    return " ".join(words)


def build_uniform_distribution() -> dict[str, float]:
    uniform_value = round(100.0 / len(ascii_uppercase), 2)
    return {letter: uniform_value for letter in ascii_uppercase}


def build_uniform_bigram_distribution() -> dict[str, float]:
    bigrams = [f"{first}{second}" for first in ascii_uppercase for second in ascii_uppercase]
    uniform_value = round(100.0 / len(bigrams), 4)
    return {bigram: uniform_value for bigram in bigrams}


@st.cache_data(show_spinner=False)
def calculate_frequency_distribution(
    text: str,
    position_mode: str,
    minimum_length: int | None,
    exact_length: int | None,
) -> dict[str, float]:
    counts = {letter: 0 for letter in ascii_uppercase}

    if position_mode == "all":
        for character in text:
            upper = character.upper()
            if upper in counts:
                counts[upper] += 1
    else:
        words = re.findall(r"[A-Za-z]+", text)
        filtered_words: list[str] = []
        for word in words:
            if minimum_length is not None and len(word) < minimum_length:
                continue
            if exact_length is not None and len(word) != exact_length:
                continue
            filtered_words.append(word)

        for word in filtered_words:
            selected_character = word[0] if position_mode == "initial" else word[-1]
            upper = selected_character.upper()
            if upper in counts:
                counts[upper] += 1

    total = sum(counts.values())
    return {
        letter: round((counts[letter] / total * 100.0) if total else 0.0, 2)
        for letter in ascii_uppercase
    }


def build_frequency_table(
    cryptogram_text: str,
    corpus_text: str | None,
    position_mode: str,
    minimum_length: int | None,
    exact_length: int | None,
    cryptogram_column_name: str,
    corpus_column_name: str,
) -> pd.DataFrame:
    cryptogram_distribution = calculate_frequency_distribution(
        cryptogram_text,
        position_mode,
        minimum_length,
        exact_length,
    )

    if corpus_text:
        corpus_distribution = calculate_frequency_distribution(
            corpus_text,
            position_mode,
            minimum_length,
            exact_length,
        )
    else:
        corpus_distribution = build_uniform_distribution()

    rows = []
    for letter in ascii_uppercase:
        rows.append(
            {
                "Cipher Token": letter,
                cryptogram_column_name: cryptogram_distribution[letter],
                corpus_column_name: corpus_distribution[letter],
            }
        )

    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def calculate_bigram_frequency_distribution(
    text: str,
    position_mode: str,
) -> dict[str, float]:
    bigrams = [f"{first}{second}" for first in ascii_uppercase for second in ascii_uppercase]
    counts = {bigram: 0 for bigram in bigrams}

    words = re.findall(r"[A-Za-z]+", text)

    if position_mode == "all":
        for word in words:
            upper_word = word.upper()
            if len(upper_word) < 2:
                continue
            for index in range(len(upper_word) - 1):
                bigram = upper_word[index : index + 2]
                if bigram in counts:
                    counts[bigram] += 1
    elif position_mode == "initial":
        for word in words:
            upper_word = word.upper()
            if len(upper_word) < 2:
                continue
            bigram = upper_word[:2]
            if bigram in counts:
                counts[bigram] += 1
    else:
        for word in words:
            upper_word = word.upper()
            if len(upper_word) < 2:
                continue
            bigram = upper_word[-2:]
            if bigram in counts:
                counts[bigram] += 1

    total = sum(counts.values())
    return {
        bigram: round((counts[bigram] / total * 100.0) if total else 0.0, 4)
        for bigram in bigrams
    }


def build_bigram_frequency_table(
    cryptogram_text: str,
    corpus_text: str | None,
    position_mode: str,
    cryptogram_column_name: str,
    corpus_column_name: str,
) -> pd.DataFrame:
    cryptogram_distribution = calculate_bigram_frequency_distribution(
        cryptogram_text,
        position_mode,
    )

    if corpus_text:
        corpus_distribution = calculate_bigram_frequency_distribution(
            corpus_text,
            position_mode,
        )
    else:
        corpus_distribution = build_uniform_bigram_distribution()

    rows = []
    for first in ascii_uppercase:
        for second in ascii_uppercase:
            bigram = f"{first}{second}"
            rows.append(
                {
                    "Cipher Token": bigram,
                    cryptogram_column_name: cryptogram_distribution[bigram],
                    corpus_column_name: corpus_distribution[bigram],
                }
            )

    return pd.DataFrame(rows)


def resolve_selected_corpus_text() -> str | None:
    corpus_source_options = [
        "NLTK Corpus Brown (default)",
        "NLTK Corpus Gutenberg",
        "NLTK Corpus Reuters",
        "NLTK Corpus Inaugural",
        "NLTK Corpus State of the Union",
        "NLTK Corpus Webtext",
        UPLOAD_PLAIN_TEXT_OPTION,
    ]

    corpus_source = st.selectbox(
        "Corpus source",
        options=corpus_source_options,
        key="corpus_source_selection",
    )

    if corpus_source == UPLOAD_PLAIN_TEXT_OPTION:
        uploaded_corpus = st.file_uploader("Upload corpus text (.txt)", type=["txt"])
        if uploaded_corpus is not None:
            st.caption(f"Active corpus: Uploaded text ({uploaded_corpus.name})")
            return uploaded_corpus.getvalue().decode("utf-8", errors="replace").replace("\r\n", "\n")

        st.caption("Upload a corpus text file to use custom corpus frequencies.")
        st.caption("Active corpus: Uniform placeholder (no uploaded corpus selected)")
        return None

    selected_nltk_corpus_label = corpus_source.removeprefix("NLTK Corpus ").replace(" (default)", "")
    selected_nltk_corpus_resource = NLTK_CORPUS_OPTIONS[selected_nltk_corpus_label]

    try:
        corpus_text = load_nltk_corpus_text(selected_nltk_corpus_resource)
        st.caption(f"Active corpus: NLTK {selected_nltk_corpus_label}")
        return corpus_text
    except RuntimeError as error:
        st.warning(f"{error} Using a uniform corpus placeholder instead.")
        st.caption(f"Active corpus: Uniform placeholder ({selected_nltk_corpus_label} unavailable)")
        return None


def render_data_sheets() -> str | None:
    st.subheader("Data sheets", anchor=False)

    selected_sheet = st.selectbox(
        "Select data sheet",
        options=[
            "None",
            "General Characteristic Frequencies",
            "Initial Position Frequencies for Long Words",
            "Terminal Position Frequencies for Long Words",
            "Initial Position Frequencies for 2-Letter Words",
            "Terminal Position Frequencies for 2-Letter Words",
            "General Characteristic Bigram Frequencies",
            "Initial Bigram Frequencies",
            "Terminal Bigram Frequencies",
        ],
        key="data_sheet_selection",
    )

    if selected_sheet == "None":
        st.caption("Select a data sheet to load corpus-based frequency comparisons.")
        return None

    corpus_text = resolve_selected_corpus_text()

    if not st.session_state.cryptogram_text:
        st.caption("Load a .txt cryptogram file to display data sheets.")
        return corpus_text

    sheet_config = {
        "General Characteristic Frequencies": {
            "position_mode": "all",
            "minimum_length": None,
            "exact_length": None,
            "cryptogram_column": "Cryptogram frequency (%)",
            "corpus_column": "Corpus frequency (%)",
        },
        "Initial Position Frequencies for Long Words": {
            "position_mode": "initial",
            "minimum_length": 4,
            "exact_length": None,
            "cryptogram_column": "Cryptogram initial frequency (%)",
            "corpus_column": "Corpus initial frequency (%)",
        },
        "Terminal Position Frequencies for Long Words": {
            "position_mode": "terminal",
            "minimum_length": 4,
            "exact_length": None,
            "cryptogram_column": "Cryptogram terminal frequency (%)",
            "corpus_column": "Corpus terminal frequency (%)",
        },
        "Initial Position Frequencies for 2-Letter Words": {
            "position_mode": "initial",
            "minimum_length": None,
            "exact_length": 2,
            "cryptogram_column": "Cryptogram initial frequency (%)",
            "corpus_column": "Corpus initial frequency (%)",
        },
        "Terminal Position Frequencies for 2-Letter Words": {
            "unit": "letter",
            "position_mode": "terminal",
            "minimum_length": None,
            "exact_length": 2,
            "cryptogram_column": "Cryptogram terminal frequency (%)",
            "corpus_column": "Corpus terminal frequency (%)",
        },
        "General Characteristic Bigram Frequencies": {
            "unit": "bigram",
            "position_mode": "all",
            "cryptogram_column": "Cryptogram bigram frequency (%)",
            "corpus_column": "Corpus bigram frequency (%)",
        },
        "Initial Bigram Frequencies": {
            "unit": "bigram",
            "position_mode": "initial",
            "cryptogram_column": "Cryptogram initial bigram frequency (%)",
            "corpus_column": "Corpus initial bigram frequency (%)",
        },
        "Terminal Bigram Frequencies": {
            "unit": "bigram",
            "position_mode": "terminal",
            "cryptogram_column": "Cryptogram terminal bigram frequency (%)",
            "corpus_column": "Corpus terminal bigram frequency (%)",
        },
    }

    for sheet_name in [
        "General Characteristic Frequencies",
        "Initial Position Frequencies for Long Words",
        "Terminal Position Frequencies for Long Words",
        "Initial Position Frequencies for 2-Letter Words",
    ]:
        sheet_config[sheet_name]["unit"] = "letter"

    config = sheet_config[selected_sheet]

    if config["unit"] == "bigram":
        st.caption("Bigram = two adjacent letters within a word (no spaces).")

    if config["unit"] == "letter":
        frequency_table = build_frequency_table(
            cryptogram_text=st.session_state.cryptogram_text,
            corpus_text=corpus_text,
            position_mode=config["position_mode"],
            minimum_length=config.get("minimum_length"),
            exact_length=config.get("exact_length"),
            cryptogram_column_name=config["cryptogram_column"],
            corpus_column_name=config["corpus_column"],
        )
        number_format = "%.2f%%"
    else:
        frequency_table = build_bigram_frequency_table(
            cryptogram_text=st.session_state.cryptogram_text,
            corpus_text=corpus_text,
            position_mode=config["position_mode"],
            cryptogram_column_name=config["cryptogram_column"],
            corpus_column_name=config["corpus_column"],
        )
        number_format = "%.4f%%"

    identifier_column = "Cipher Token"
    cryptogram_ranked_tokens = frequency_table.sort_values(
        by=[config["cryptogram_column"], identifier_column],
        ascending=[False, True],
    )[identifier_column].tolist()
    corpus_ranked_tokens = frequency_table.sort_values(
        by=[config["corpus_column"], identifier_column],
        ascending=[False, True],
    )[identifier_column].tolist()

    default_sort_column = "Cryptogram initial frequency (%)"
    sort_column = default_sort_column if default_sort_column in frequency_table.columns else config["cryptogram_column"]
    frequency_table = frequency_table.sort_values(
        by=[sort_column, identifier_column],
        ascending=[False, True],
    ).reset_index(drop=True)

    frequency_table["Same-rank corpus token"] = corpus_ranked_tokens[: len(frequency_table)]
    frequency_table["Same-rank cryptogram token"] = cryptogram_ranked_tokens[: len(frequency_table)]
    frequency_table = frequency_table[
        [
            identifier_column,
            "Same-rank corpus token",
            "Same-rank cryptogram token",
            config["cryptogram_column"],
            config["corpus_column"],
        ]
    ]

    st.caption(
        "Same-rank corpus token and same-rank cryptogram token are aligned by their respective frequency ranks "
        "(ties broken alphabetically)."
    )

    st.dataframe(
        frequency_table,
        hide_index=True,
        use_container_width=True,
        column_config={
            config["cryptogram_column"]: st.column_config.NumberColumn(format=number_format),
            config["corpus_column"]: st.column_config.NumberColumn(format=number_format),
        },
    )

    return corpus_text


def render_pattern_assistant(corpus_text: str | None) -> None:
    st.markdown("**Pattern assistant**")

    scan_mode = st.segmented_control(
        "Scan mode",
        options=["Full scan", "Fast scan"],
        key="pattern_scan_mode",
    )

    max_bucket_scan = None if scan_mode == "Full scan" else PATTERN_FAST_MAX_SCAN_PER_BUCKET

    if not st.session_state.cryptogram_text:
        st.caption("Load a cryptogram to generate pattern candidates.")
        return

    if not corpus_text:
        st.caption("Select or upload a corpus in Data sheets to enable pattern candidates.")
        return

    words = [word for word in re.findall(r"[A-Za-z]+", st.session_state.cryptogram_text) if len(word) >= 4]
    if not words:
        st.caption("No alphabetic words of length 4 or greater found in the active cryptogram.")
        return

    unique_words: list[str] = []
    seen_words: set[str] = set()
    for word in words:
        normalized = word.upper()
        if normalized not in seen_words:
            seen_words.add(normalized)
            unique_words.append(word)

    pattern_index, index_metrics = build_corpus_pattern_index(corpus_text)
    candidate_rows: list[dict[str, str]] = []
    total_scanned = 0
    evaluated_words = 0
    capped_bucket_count = 0

    for cipher_word in unique_words:
        shape_signature = build_word_shape_signature(cipher_word)
        if not has_repeated_shape_letters(shape_signature):
            continue

        solved_count = sum(
            1 for character in cipher_word.upper() if st.session_state.substitutions.get(character, "")
        )

        if solved_count == len(cipher_word):
            continue

        evaluated_words += 1

        solved_pattern = "".join(
            st.session_state.substitutions.get(character.upper(), "") or "_"
            for character in cipher_word
        )

        candidates, scanned_count, bucket_size = resolve_pattern_candidates(
            cipher_word,
            st.session_state.substitutions,
            pattern_index,
            max_bucket_scan=max_bucket_scan,
        )
        total_scanned += scanned_count
        if max_bucket_scan is not None and bucket_size > max_bucket_scan:
            capped_bucket_count += 1

        candidate_rows.append(
            {
                "Cipher word": cipher_word.upper(),
                "Shape signature": shape_signature,
                "Solved pattern": solved_pattern,
                "Bucket size": f"{bucket_size:,}",
                "Candidates": ", ".join(candidate.upper() for candidate in candidates) if candidates else "—",
            }
        )

    if not candidate_rows:
        st.caption("All words are fully solved or no candidates are available.")
        return

    average_scanned = round((total_scanned / evaluated_words), 2) if evaluated_words else 0.0
    metrics_columns = st.columns(5)
    metrics_columns[0].metric("Corpus unique words", f"{index_metrics['unique_words']:,}")
    metrics_columns[1].metric("Indexed words", f"{index_metrics['indexed_words']:,}")
    metrics_columns[2].metric("Shape buckets", f"{index_metrics['shape_buckets']:,}")
    metrics_columns[3].metric("Avg scanned / word", f"{average_scanned:,}")
    metrics_columns[4].metric("Capped buckets", capped_bucket_count)

    if max_bucket_scan is None:
        mode_caption = "Per-word candidate scans evaluate the full matching bucket."
    else:
        mode_caption = (
            f"Per-word candidate scans are capped at {PATTERN_FAST_MAX_SCAN_PER_BUCKET:,} "
            f"for Fast scan mode."
        )

    st.caption(
        f"Pattern index is cached by corpus text. Largest bucket size: {index_metrics['largest_bucket']:,}. "
        f"{mode_caption}"
    )

    candidate_frame = pd.DataFrame(candidate_rows).head(PATTERN_MAX_ROWS)
    st.dataframe(candidate_frame, hide_index=True)


def render_ngram_score_panel() -> None:
    st.markdown("**N-gram score**")

    if not st.session_state.cryptogram_text:
        st.caption("Load a cryptogram to score substitution quality.")
        return

    plaintext_preview = build_plaintext_preview(st.session_state.cryptogram_text, st.session_state.substitutions)
    segments = re.findall(r"[A-Za-z]{2,}", plaintext_preview)

    bigrams: list[str] = []
    trigrams: list[str] = []
    for segment in segments:
        upper_segment = segment.upper()
        bigrams.extend(upper_segment[index : index + 2] for index in range(len(upper_segment) - 1))
        trigrams.extend(upper_segment[index : index + 3] for index in range(len(upper_segment) - 2))

    bigram_hits = sum(1 for gram in bigrams if gram in COMMON_BIGRAMS)
    trigram_hits = sum(1 for gram in trigrams if gram in COMMON_TRIGRAMS)

    bigram_score = round((bigram_hits / len(bigrams) * 100.0) if bigrams else 0.0, 2)
    trigram_score = round((trigram_hits / len(trigrams) * 100.0) if trigrams else 0.0, 2)
    solved_letters = sum(1 for value in st.session_state.substitutions.values() if value)

    metric_columns = st.columns(3)
    metric_columns[0].metric("Solved mappings", solved_letters)
    metric_columns[1].metric("Bigram match", f"{bigram_score:.2f}%")
    metric_columns[2].metric("Trigram match", f"{trigram_score:.2f}%")

    st.caption("Higher bigram/trigram matches generally indicate more English-like substitutions.")


def render_per_word_progress_panel() -> None:
    st.markdown("**Per-word solve progress**")

    if not st.session_state.cryptogram_text:
        st.caption("Load a cryptogram to see word-by-word progress.")
        return

    words = re.findall(r"[A-Za-z]+", st.session_state.cryptogram_text)
    progress_rows: list[dict[str, str | float | int]] = []

    for index, word in enumerate(words, start=1):
        solved_count = sum(1 for character in word.upper() if st.session_state.substitutions.get(character, ""))
        solved_pct = round((solved_count / len(word) * 100.0) if word else 0.0, 2)
        preview = "".join(
            st.session_state.substitutions.get(character.upper(), "") or "_"
            for character in word
        )
        progress_rows.append(
            {
                "Word #": index,
                "Cipher word": word.upper(),
                "Preview": preview,
                "Solved %": solved_pct,
            }
        )

    if not progress_rows:
        st.caption("No words detected in the active cryptogram.")
        return

    progress_frame = pd.DataFrame(progress_rows).sort_values(by=["Solved %", "Word #"], ascending=[True, True])
    st.dataframe(
        progress_frame,
        hide_index=True,
        column_config={"Solved %": st.column_config.NumberColumn(format="%.2f%%")},
    )


def render_neighborhood_panel() -> None:
    st.markdown("**Cipher letter neighborhoods**")

    if not st.session_state.cryptogram_text:
        st.caption("Load a cryptogram to inspect neighboring letter patterns.")
        return

    previous_counts: dict[str, Counter[str]] = {letter: Counter() for letter in ALPHABET_ASCENDING}
    next_counts: dict[str, Counter[str]] = {letter: Counter() for letter in ALPHABET_ASCENDING}

    words = re.findall(r"[A-Za-z]+", st.session_state.cryptogram_text.upper())
    for word in words:
        for index, letter in enumerate(word):
            if index > 0:
                previous_counts[letter][word[index - 1]] += 1
            if index < len(word) - 1:
                next_counts[letter][word[index + 1]] += 1

    neighborhood_rows: list[dict[str, str]] = []
    for letter in ALPHABET_ASCENDING:
        top_previous = ", ".join(f"{char}({count})" for char, count in previous_counts[letter].most_common(3)) or "—"
        top_next = ", ".join(f"{char}({count})" for char, count in next_counts[letter].most_common(3)) or "—"
        neighborhood_rows.append(
            {
                "Letter": letter,
                "Most common previous": top_previous,
                "Most common next": top_next,
            }
        )

    st.dataframe(pd.DataFrame(neighborhood_rows), hide_index=True)


def render_likely_rejected_checks_panel() -> None:
    st.markdown("**Likely / rejected checks**")

    overlapping_rows: list[dict[str, str]] = []
    for letter in ALPHABET_ASCENDING:
        likely_set = set(st.session_state.likely_chars[letter])
        rejected_set = set(st.session_state.rejected_chars[letter])
        overlap = sorted(likely_set & rejected_set)
        if overlap:
            overlapping_rows.append(
                {
                    "Cipher letter": letter,
                    "Overlap": " ".join(overlap),
                }
            )

    if not overlapping_rows:
        st.success("No overlaps between likely and rejected sets.")
        return

    st.warning("Some letters appear in both likely and rejected fields.")
    st.dataframe(pd.DataFrame(overlapping_rows), hide_index=True)


def render_analysis_panels(corpus_text: str | None) -> None:
    st.subheader("Analysis", anchor=False)

    tab_patterns, tab_score, tab_progress, tab_neighborhoods, tab_quality = st.tabs(
        [
            "Pattern assistant",
            "N-gram score",
            "Word progress",
            "Neighborhoods",
            "Quality checks",
        ]
    )

    with tab_patterns:
        render_pattern_assistant(corpus_text)
    with tab_score:
        render_ngram_score_panel()
    with tab_progress:
        render_per_word_progress_panel()
    with tab_neighborhoods:
        render_neighborhood_panel()
    with tab_quality:
        render_likely_rejected_checks_panel()


def render_session_state_tools() -> None:
    st.subheader("Session state", anchor=False)

    if st.session_state.session_import_notice:
        st.success("Session imported.")
        st.session_state.session_import_notice = False

    payload = export_session_payload()
    payload_json = json.dumps(payload, indent=2)

    st.download_button(
        "Export session JSON",
        data=payload_json,
        file_name="cryptogram_session.json",
        mime="application/json",
    )

    imported_file = st.file_uploader("Import session JSON", type=["json"], key="session_import_uploader")
    if imported_file is None:
        st.caption("Upload a session JSON exported from this app.")
        return

    try:
        decoded_payload = json.loads(imported_file.getvalue().decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        st.error("Uploaded file is not valid JSON.")
        return

    if not isinstance(decoded_payload, dict):
        st.error("Session JSON must be an object.")
        return

    if st.button("Apply imported session"):
        st.session_state.pending_session_import_payload = decoded_payload
        st.rerun()


def render_mapping_grid() -> None:
    st.subheader("Letter mapping (A → Z)", anchor=False)
    st.caption("Only A-Z characters are accepted in Substitution, Likely, and Tested / Rejected fields.")

    conflicts = compute_substitution_conflicts(st.session_state.substitutions)
    self_substitutions = compute_self_substitutions(st.session_state.substitutions)
    conflict_letters = sorted(conflicts)
    if conflict_letters:
        conflict_preview = ", ".join(conflict_letters[:10])
        suffix = "..." if len(conflict_letters) > 10 else ""
        st.warning(f"Conflicts detected for: {conflict_preview}{suffix}")
    else:
        st.success("No substitution conflicts detected.")

    if self_substitutions:
        self_preview = ", ".join(sorted(self_substitutions)[:10])
        self_suffix = "..." if len(self_substitutions) > 10 else ""
        st.warning(f"Self-substitutions detected for: {self_preview}{self_suffix}")

    header_columns = st.columns([0.7, 0.9, 1.0, 1.2, 1.2, 0.9])
    header_columns[0].markdown("<span style='white-space: nowrap; font-weight: 700;'>Alphabet</span>", unsafe_allow_html=True)
    header_columns[1].markdown("**Status**")
    header_columns[2].markdown("**Lock**")
    header_columns[3].markdown("**Substitution**")
    header_columns[4].markdown("**Likely**")
    header_columns[5].markdown("**Tested / Rejected**")

    with st.container(height=740, gap=None):
        for letter in ALPHABET_ASCENDING:
            row_columns = st.columns([0.7, 0.9, 1.0, 1.2, 1.2, 0.9])

            row_columns[0].markdown(f"**{letter}**")

            if letter in conflicts:
                row_columns[1].markdown(":orange-badge[conflict]")
            elif letter in self_substitutions:
                row_columns[1].markdown(":red-badge[self]")
            elif st.session_state.locked_letters[letter]:
                row_columns[1].markdown(":blue-badge[locked]")
            else:
                row_columns[1].markdown(":gray-badge[ok]")

            lock_key = f"lock_{letter}"
            row_columns[2].checkbox(
                f"Lock {letter}",
                key=lock_key,
                label_visibility="collapsed",
                on_change=on_lock_change,
                args=(letter,),
            )
            st.session_state.locked_letters[letter] = bool(st.session_state[lock_key])

            sub_key = f"sub_{letter}"
            row_columns[3].text_input(
                f"Substitution for {letter}",
                key=sub_key,
                label_visibility="collapsed",
                max_chars=1,
                placeholder="A-Z",
                on_change=on_substitution_change,
                args=(letter,),
                disabled=st.session_state.locked_letters[letter],
            )
            st.session_state.substitutions[letter] = normalize_single_letter(st.session_state[sub_key])

            likely_key = f"likely_{letter}"
            row_columns[4].text_input(
                f"Likely values for {letter}",
                key=likely_key,
                label_visibility="collapsed",
                placeholder="Possible letters",
                on_change=on_likely_change,
                args=(letter,),
                disabled=st.session_state.locked_letters[letter],
            )
            st.session_state.likely_chars[letter] = normalize_multi_entry(st.session_state[likely_key])

            rejected_key = f"rejected_{letter}"
            row_columns[5].text_input(
                f"Rejected values for {letter}",
                key=rejected_key,
                label_visibility="collapsed",
                placeholder="Tried/rejected",
                on_change=on_rejected_change,
                args=(letter,),
                disabled=st.session_state.locked_letters[letter],
            )
            st.session_state.rejected_chars[letter] = normalize_multi_entry(st.session_state[rejected_key])

def apply_page_styles(theme_name: str) -> None:
    theme = THEME_PRESETS.get(theme_name, THEME_PRESETS["Paper & Ink"])

    st.markdown(
        f"""
        <style>
        :root {{
            --app-bg: {theme["app_bg"]};
            --app-fg: {theme["app_fg"]};
            --panel-bg: {theme["panel_bg"]};
            --panel-border: {theme["panel_border"]};
            --display-bg: {theme["display_bg"]};
            --display-border: {theme["display_border"]};
            --sub-color: {theme["sub_color"]};
            --unsolved-color: {theme["unsolved_color"]};
            --button-bg: {theme["button_bg"]};
            --button-fg: {theme["button_fg"]};
            --button-border: {theme["button_border"]};
        }}

        .stApp {{
            background: var(--app-bg);
            color: var(--app-fg);
        }}

        .block-container {{
            padding-top: 3.25rem;
            padding-bottom: 1rem;
        }}

        h1 {{
            margin-top: 0.25rem;
        }}

        div[data-testid="stVerticalBlockBorderWrapper"] {{
            background: var(--panel-bg);
            border-color: var(--panel-border);
        }}

        .cryptogram-display {{
            min-height: 130px;
            border: 1px solid var(--display-border);
            border-radius: 8px;
            background: var(--display-bg);
            padding: 0.75rem;
            white-space: pre-wrap;
            line-height: 1.95;
            font-family: Consolas, "Courier New", monospace;
        }}

        .sub-letter {{
            font-weight: 700;
            color: var(--sub-color);
        }}

        .unsolved-letter {{
            color: var(--unsolved-color);
            font-weight: 500;
            opacity: 0.65;
        }}

        div[data-testid="stTextInput"] {{
            margin-top: 0.1rem;
            margin-bottom: 0.1rem;
        }}

        div[data-testid="stTextInput"] input {{
            min-height: 2rem;
            padding-top: 0.25rem;
            padding-bottom: 0.25rem;
        }}

        div[data-testid="stColumn"] p {{
            margin-top: 0.2rem;
            margin-bottom: 0.2rem;
        }}

        div[data-testid="stButton"] > button {{
            background: var(--button-bg);
            color: var(--button-fg);
            border: 1px solid var(--button-border);
        }}

        div[data-testid="stButton"] > button:hover {{
            border-color: var(--sub-color);
            color: var(--button-fg);
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="Cryptogram Workspace", page_icon=":material/key:", layout="wide")
    initialize_state()
    seed_defaults_on_first_load()
    apply_pending_session_import()
    initialize_mapping_history()

    st.title("Cryptogram Workspace", text_alignment="center")
    st.caption("Load a cryptogram, test substitutions, and compare frequency-based clues.", text_alignment="center")

    theme_left, theme_center, theme_right = st.columns([1.6, 1.2, 1.6])
    with theme_center:
        selected_theme = st.segmented_control(
            "Theme",
            options=["Paper & Ink", "Nord Cipher"],
            key="visual_theme",
        )

    apply_page_styles(selected_theme)

    top_left, top_center, top_right = st.columns([1.25, 1.5, 1.25])
    with top_center:
        with st.container(border=True):
            load_uploaded_text()

    left_column, right_column = st.columns([2.0, 1.35], vertical_alignment="top")

    with left_column:
        with st.container(border=True):
            render_original_cryptogram()

        with st.container(border=True):
            render_substitution_cryptogram()

        with st.container(border=True):
            active_corpus_text = render_data_sheets()

    with right_column:
        with st.container(border=True):
            with st.container(horizontal=True, horizontal_alignment="distribute"):
                st.button("Reset mappings", on_click=reset_mappings)
                st.button("Reset all", on_click=reset_all)
                st.button(
                    "Undo",
                    on_click=undo_mapping_change,
                    disabled=st.session_state.mapping_history_index <= 0,
                )
                st.button(
                    "Redo",
                    on_click=redo_mapping_change,
                    disabled=st.session_state.mapping_history_index >= len(st.session_state.mapping_history) - 1,
                )
            render_mapping_grid()

        with st.container(border=True):
            render_analysis_panels(active_corpus_text)

        with st.container(border=True):
            render_session_state_tools()


if __name__ == "__main__":
    main()
