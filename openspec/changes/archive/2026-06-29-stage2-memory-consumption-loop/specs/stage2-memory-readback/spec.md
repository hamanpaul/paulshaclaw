## MODIFIED Requirements

### Requirement: Wake-up brief read-back injection

On session start, the memory wake-up hook SHALL resolve the session's project and return a concise **orientation** as injected context: a short note that memory is active for the project (with active note count) and that task-relevant memories will surface per-prompt as a shortlist whose listed absolute paths the agent can Read to consume. The SessionStart brief SHALL NOT dump the project MOC or a large recent-slices list, and SHALL NOT prepend a 16-hex citation preamble. When the project cannot be resolved or has no memory, the hook SHALL return empty context. The hook SHALL NOT block, fail, or otherwise disrupt the agent session.

#### Scenario: Known project yields a concise orientation
- **WHEN** a session starts in a directory that resolves to a project with existing knowledge atoms
- **THEN** the hook returns injected context that is a short orientation (memory active, note count, per-prompt shortlist + Read-to-consume hint) and does NOT contain a full project MOC dump or a 16-hex citation preamble

#### Scenario: Unknown or empty project yields empty context
- **WHEN** a session starts in a directory that resolves to no project, or to a project with no atoms
- **THEN** the hook returns empty injected context and the session proceeds normally
