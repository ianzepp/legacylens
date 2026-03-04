from dataclasses import dataclass, field


@dataclass
class CodeChunk:
    content: str
    file_path: str
    file_name: str
    file_type: str  # cbl, cpy, bms, jcl
    chunk_type: str  # header, data_division, paragraph, copybook, bms_map, jcl_step
    name: str  # paragraph name, copybook name, etc.
    start_line: int
    end_line: int
    preamble: str = ""
    summary: str = ""
    parent_program: str = ""
    comments: str = ""
    copy_references: list[str] = field(default_factory=list)
    calls_to: list[str] = field(default_factory=list)


@dataclass
class QueryResult:
    content: str
    file_path: str
    file_name: str
    file_type: str
    chunk_type: str
    name: str
    start_line: int
    end_line: int
    score: float
    preamble: str = ""
    summary: str = ""
    comments: str = ""
    copy_references: list[str] = field(default_factory=list)
    calls_to: list[str] = field(default_factory=list)
