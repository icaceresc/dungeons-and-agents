//! The campaign's name for what an agent's tool does: a skill, always shown
//! with the tool itself ("Hechizo (Bash)"), so a reader learns the skills from
//! the tools they know. The one table every reader of a running tool names it
//! by: the footer's tally, the tooltip and the dashboard.

use pixtuoid_core::state::ToolKind;

/// What a tool does, in the campaign's words.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Skill {
    /// A shell command.
    Hechizo,
    /// A file written or edited.
    Golpe,
    /// A file, a listing or an image read.
    Estudio,
    /// A search through the code.
    Rastreo,
    /// A page fetched or the web searched.
    Exploracion,
    /// A subagent sent off.
    Invocacion,
    /// A plan or a to-do list kept.
    Tactica,
    /// An MCP server's tool.
    Ritual,
    /// Any other tool.
    Habilidad,
}

impl Skill {
    /// Its name as the screen writes it.
    pub fn name(self) -> &'static str {
        match self {
            Skill::Hechizo => "Hechizo",
            Skill::Golpe => "Golpe",
            Skill::Estudio => "Estudio",
            Skill::Rastreo => "Rastreo",
            Skill::Exploracion => "Exploración",
            Skill::Invocacion => "Invocación",
            Skill::Tactica => "Táctica",
            Skill::Ritual => "Ritual",
            Skill::Habilidad => "Habilidad",
        }
    }

    /// The skill `tool` (a tool's name, as its source names it) uses, its
    /// call's `kind` deciding a delegation, which displays no tool. The names
    /// are each CLI's own: Claude Code's, Codex's, OpenCode's, Antigravity's
    /// and the other sources' generic ones.
    pub fn of(tool: &str, kind: ToolKind) -> Self {
        if kind == ToolKind::Task {
            return Skill::Invocacion;
        }
        let tool = tool.to_ascii_lowercase();
        if tool.starts_with("mcp_") {
            return Skill::Ritual;
        }
        if tool.starts_with("browser_") {
            return Skill::Exploracion;
        }
        match tool.as_str() {
            // `orca`: what the Orca adapter names an Orca CLI call.
            "bash" | "bashoutput" | "killshell" | "killbash" | "powershell" | "shell"
            | "local_shell" | "exec" | "exec_command" | "write_stdin" | "run_command"
            | "send_command_input" | "command_status" | "orca" => Skill::Hechizo,
            "edit"
            | "write"
            | "multiedit"
            | "notebookedit"
            | "apply_patch"
            | "patch"
            | "create"
            | "str_replace"
            | "str_replace_editor"
            | "insert"
            | "write_to_file"
            | "replace_file_content"
            | "multi_replace_file_content" => Skill::Golpe,
            "read" | "notebookread" | "view" | "view_image" | "ls" | "list" | "read_file"
            | "view_file" | "view_file_outline" | "view_code_item" | "list_dir" => Skill::Estudio,
            "grep" | "glob" | "search" | "find" | "codesearch" | "grep_search" | "find_by_name"
            | "codebase_search" => Skill::Rastreo,
            "webfetch" | "websearch" | "web_fetch" | "web_search" | "read_url_content"
            | "search_web" => Skill::Exploracion,
            "task" | "agent" | "spawn_agent" | "subagent" => Skill::Invocacion,
            "todowrite" | "todoread" | "update_plan" | "exitplanmode" | "plan" => Skill::Tactica,
            _ => Skill::Habilidad,
        }
    }
}

/// The tool a running item's display `detail` names: the identifier it
/// opens with (every source writes `<tool>: <target>`), empty for a detail
/// that opens with none.
pub fn tool_of(detail: &str) -> &str {
    let end = detail
        .find(|c: char| !(c.is_alphanumeric() || c == '_' || c == '-'))
        .unwrap_or(detail.len());
    &detail[..end]
}

/// `tool` named as its skill, the tool beside it: `Hechizo (Bash)`; a
/// delegation, which names no tool, its skill alone.
pub fn label(tool: &str, kind: ToolKind) -> String {
    let skill = Skill::of(tool, kind);
    if kind == ToolKind::Task || tool.is_empty() {
        skill.name().to_owned()
    } else {
        format!("{} ({tool})", skill.name())
    }
}

/// A running item's display `detail` with its tool named as its skill:
/// `Bash: cargo test` reads `Hechizo (Bash): cargo test`.
pub fn skilled(detail: &str, kind: ToolKind) -> String {
    let tool = tool_of(detail);
    if kind == ToolKind::Task {
        return label(tool, kind);
    }
    format!("{}{}", label(tool, kind), &detail[tool.len()..])
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Each CLI's own tool names land on the skill that does what they do,
    /// and an unknown tool on the generic one.
    #[test]
    fn every_sources_tools_have_their_skill() {
        let rows: &[(Skill, &[&str])] = &[
            (
                Skill::Hechizo,
                &[
                    "Bash",
                    "BashOutput",
                    "KillShell",
                    "shell",
                    "exec_command",
                    "write_stdin",
                    "exec",
                    "bash",
                    "run_command",
                    "PowerShell",
                    "Orca",
                ],
            ),
            (
                Skill::Golpe,
                &[
                    "Edit",
                    "Write",
                    "MultiEdit",
                    "NotebookEdit",
                    "apply_patch",
                    "edit",
                    "write",
                    "patch",
                    "write_to_file",
                    "replace_file_content",
                    "multi_replace_file_content",
                ],
            ),
            (
                Skill::Estudio,
                &[
                    "Read",
                    "view_image",
                    "read",
                    "list",
                    "view_file",
                    "read_file",
                    "list_dir",
                ],
            ),
            (
                Skill::Rastreo,
                &[
                    "Grep",
                    "Glob",
                    "grep",
                    "glob",
                    "grep_search",
                    "find_by_name",
                ],
            ),
            (
                Skill::Exploracion,
                &[
                    "WebFetch",
                    "WebSearch",
                    "web_search",
                    "webfetch",
                    "read_url_content",
                    "search_web",
                    "browser_navigate",
                ],
            ),
            (
                Skill::Tactica,
                &["TodoWrite", "update_plan", "todowrite", "ExitPlanMode"],
            ),
            (
                Skill::Ritual,
                &["mcp__orca__send_message", "mcp_github_search"],
            ),
            (Skill::Habilidad, &["frobnicate", "", "Delegating"]),
        ];
        for &(skill, tools) in rows {
            for tool in tools {
                assert_eq!(Skill::of(tool, ToolKind::Other), skill, "{tool:?}");
            }
        }
        assert_eq!(
            Skill::of("Delegating", ToolKind::Task),
            Skill::Invocacion,
            "a delegation is a summons whatever it displays"
        );
    }

    /// A tool reads as its skill with the tool beside it, a detail keeps
    /// its target, and a delegation names its skill alone.
    #[test]
    fn a_tool_reads_as_its_skill_with_the_tool_beside_it() {
        assert_eq!(label("Bash", ToolKind::Bash), "Hechizo (Bash)");
        assert_eq!(label("Edit", ToolKind::Edit), "Golpe (Edit)");
        assert_eq!(label("Orca", ToolKind::Other), "Hechizo (Orca)");
        assert_eq!(
            skilled("Bash: cargo test", ToolKind::Bash),
            "Hechizo (Bash): cargo test"
        );
        assert_eq!(
            skilled("apply_patch", ToolKind::Other),
            "Golpe (apply_patch)"
        );
        assert_eq!(skilled("Delegating", ToolKind::Task), "Invocación");
        assert_eq!(tool_of("exec: exec_command"), "exec");
        assert_eq!(
            tool_of("mcp__orca__send_message"),
            "mcp__orca__send_message"
        );
        assert_eq!(tool_of("/usr/bin/thing"), "", "a path names no tool");
    }
}
