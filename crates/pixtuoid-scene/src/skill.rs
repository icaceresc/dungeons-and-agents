//! The campaign's name for what an agent's tool does: a skill, always shown
//! with the tool itself ("Spell (Bash)"), so a reader learns the skills from
//! the tools they know. The one table every reader of a running tool names it
//! by: the footer's tally, the tooltip and the dashboard.

use pixtuoid_core::state::ToolKind;

/// What a tool does, in the campaign's words.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Skill {
    /// A shell command.
    Spell,
    /// An existing file changed.
    Transmute,
    /// A new file written.
    Conjure,
    /// A file or an image read.
    Identify,
    /// Code searched for text.
    Scry,
    /// Files found by name, or a directory's listing.
    Locate,
    /// A page fetched, the web searched or a browser driven.
    Divination,
    /// A subagent sent off.
    Summon,
    /// A plan or a to-do list kept.
    BattlePlan,
    /// An MCP server's tool.
    Ritual,
    /// An Orca CLI call: a message to the other sessions.
    Sending,
    /// Any other tool.
    Cantrip,
}

impl Skill {
    /// Its name as the screen writes it.
    pub fn name(self) -> &'static str {
        match self {
            Skill::Spell => "Spell",
            Skill::Transmute => "Transmute",
            Skill::Conjure => "Conjure",
            Skill::Identify => "Identify",
            Skill::Scry => "Scry",
            Skill::Locate => "Locate",
            Skill::Divination => "Divination",
            Skill::Summon => "Summon",
            Skill::BattlePlan => "Battle Plan",
            Skill::Ritual => "Ritual",
            Skill::Sending => "Sending",
            Skill::Cantrip => "Cantrip",
        }
    }

    /// The skill `tool` (a tool's name, as its source names it) uses, its
    /// call's `kind` deciding a delegation, which displays no tool. The names
    /// are each CLI's own: Claude Code's, Codex's, OpenCode's, Antigravity's
    /// and the other sources' generic ones.
    pub fn of(tool: &str, kind: ToolKind) -> Self {
        if kind == ToolKind::Task {
            return Skill::Summon;
        }
        let tool = tool.to_ascii_lowercase();
        if tool.starts_with("mcp_") {
            return Skill::Ritual;
        }
        if tool.starts_with("browser_") {
            return Skill::Divination;
        }
        match tool.as_str() {
            "bash" | "bashoutput" | "killshell" | "killbash" | "powershell" | "shell"
            | "local_shell" | "exec" | "exec_command" | "write_stdin" | "run_command"
            | "send_command_input" | "command_status" => Skill::Spell,
            // What the Orca adapter names an Orca CLI call.
            "orca" => Skill::Sending,
            // Changing a file that exists. Codex's `apply_patch` can also add
            // one, but a patch is mostly an edit.
            "edit"
            | "multiedit"
            | "notebookedit"
            | "apply_patch"
            | "patch"
            | "str_replace"
            | "str_replace_editor"
            | "insert"
            | "replace_file_content"
            | "multi_replace_file_content" => Skill::Transmute,
            // Writing a file whole, most often a new one.
            "write" | "create" | "write_to_file" => Skill::Conjure,
            "read" | "notebookread" | "view" | "view_image" | "read_file" | "view_file"
            | "view_file_outline" | "view_code_item" => Skill::Identify,
            "grep" | "search" | "codesearch" | "grep_search" | "codebase_search" => Skill::Scry,
            // A directory's listing finds files as a glob does; reading them
            // is Identify.
            "glob" | "find" | "find_by_name" | "ls" | "list" | "list_dir" => Skill::Locate,
            "webfetch" | "websearch" | "web_fetch" | "web_search" | "read_url_content"
            | "search_web" => Skill::Divination,
            "task" | "agent" | "spawn_agent" | "subagent" => Skill::Summon,
            "todowrite" | "todoread" | "update_plan" | "exitplanmode" | "plan" => Skill::BattlePlan,
            _ => Skill::Cantrip,
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

/// `tool` named as its skill, the tool beside it: `Spell (Bash)`; a
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
/// `Bash: cargo test` reads `Spell (Bash): cargo test`.
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
                Skill::Spell,
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
                ],
            ),
            (
                Skill::Transmute,
                &[
                    "Edit",
                    "MultiEdit",
                    "NotebookEdit",
                    "apply_patch",
                    "edit",
                    "patch",
                    "str_replace",
                    "insert",
                    "replace_file_content",
                    "multi_replace_file_content",
                ],
            ),
            (
                Skill::Conjure,
                &["Write", "write", "create", "write_to_file"],
            ),
            (
                Skill::Identify,
                &[
                    "Read",
                    "NotebookRead",
                    "view_image",
                    "read",
                    "view_file",
                    "read_file",
                ],
            ),
            (
                Skill::Scry,
                &[
                    "Grep",
                    "grep",
                    "search",
                    "codesearch",
                    "grep_search",
                    "codebase_search",
                ],
            ),
            (
                Skill::Locate,
                &[
                    "Glob",
                    "glob",
                    "find",
                    "find_by_name",
                    "ls",
                    "list",
                    "list_dir",
                ],
            ),
            (
                Skill::Divination,
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
                Skill::BattlePlan,
                &["TodoWrite", "update_plan", "todowrite", "ExitPlanMode"],
            ),
            (
                Skill::Ritual,
                &["mcp__orca__send_message", "mcp_github_search"],
            ),
            (Skill::Sending, &["Orca"]),
            (Skill::Cantrip, &["frobnicate", "", "Delegating"]),
        ];
        for &(skill, tools) in rows {
            for tool in tools {
                assert_eq!(Skill::of(tool, ToolKind::Other), skill, "{tool:?}");
            }
        }
        assert_eq!(
            Skill::of("Delegating", ToolKind::Task),
            Skill::Summon,
            "a delegation is a summons whatever it displays"
        );
    }

    /// A tool reads as its skill with the tool beside it, a detail keeps
    /// its target, and a delegation names its skill alone.
    #[test]
    fn a_tool_reads_as_its_skill_with_the_tool_beside_it() {
        assert_eq!(label("Bash", ToolKind::Bash), "Spell (Bash)");
        assert_eq!(label("Edit", ToolKind::Edit), "Transmute (Edit)");
        assert_eq!(label("Orca", ToolKind::Other), "Sending (Orca)");
        assert_eq!(
            label("TodoWrite", ToolKind::Other),
            "Battle Plan (TodoWrite)"
        );
        assert_eq!(
            skilled("Bash: cargo test", ToolKind::Bash),
            "Spell (Bash): cargo test"
        );
        assert_eq!(
            skilled("apply_patch", ToolKind::Other),
            "Transmute (apply_patch)"
        );
        assert_eq!(skilled("Delegating", ToolKind::Task), "Summon");
        assert_eq!(tool_of("exec: exec_command"), "exec");
        assert_eq!(
            tool_of("mcp__orca__send_message"),
            "mcp__orca__send_message"
        );
        assert_eq!(tool_of("/usr/bin/thing"), "", "a path names no tool");
    }
}
