-- The MCP proxy once approved proposals for its host side, which is the agent, and
-- recorded that approver as 'mcp-proxy-demo'. The agent side can no longer approve,
-- and the proxy now honours approval references, so an approval the agent granted
-- itself that is still unused is retired here rather than left presentable.
UPDATE approvals SET state = 'expired'
 WHERE state = 'approved' AND decided_by_session = 'mcp-proxy-demo';
