import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Terminal, X, ChevronRight } from 'lucide-react';
import { authFetch } from '../lib/authFetch';

/**
 * CyberTerminal — Console de commandes style CLI cyberpunk
 * Supporte : list agents, list goals, wake <id>, spawn, inspect, telemetry, help, clear
 */

const PROMPT = 'rockib@cockpit:~$ ';
const MAX_HISTORY = 200;

const HELP_TEXT = `
╔══════════════════════════════════════════════════════════════╗
║                ROCKIB IA — Terminal Cockpit                  ║
╠══════════════════════════════════════════════════════════════╣
║  list agents        — Lister tous les agents actifs          ║
║  list goals         — Lister tous les objectifs              ║
║  inspect <id>       — Inspecter un agent (premiers 8 chars)  ║
║  logs <nom/id>      — Afficher les logs récents d'un agent   ║
║  wake <goal_id>     — Déclencher un cycle d'exécution        ║
║  spawn <name>       — Créer un nouvel agent                  ║
║    --role <rôle>      (défaut: Worker)                       ║
║    --autonomy <0-5>   (défaut: 2)                            ║
║  mission <texte>    — Assigner une mission au 1er Agent      ║
║  telemetry          — Derniers événements                    ║
║  status             — Résumé système global                  ║
║  clear              — Effacer le terminal                    ║
║  help               — Afficher cette aide                    ║
╚══════════════════════════════════════════════════════════════╝
`.trim();

function formatTimestamp(ts) {
  return new Date(ts).toLocaleTimeString('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export default function CyberTerminal({
  isOpen,
  onClose,
  agents = [],
  goals = [],
  telemetry = [],
  onWakeGoal,
  onSpawnAgent,
  onSelectAgent,
  onCreateGoal,
}) {
  const [lines, setLines] = useState([
    { text: '▓▓▓ ROCKIB IA — Cockpit Terminal v1.0 ▓▓▓', color: '#00F0FF' },
    { text: 'Tapez "help" pour la liste des commandes.', color: '#64748B' },
    { text: '', color: '#64748B' },
  ]);
  const [input, setInput] = useState('');
  const [cmdHistory, setCmdHistory] = useState([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  const addLine = useCallback(
    (text, color = '#E2E8F0') => {
      setLines((prev) => {
        const next = [...prev, { text, color }];
        return next.length > MAX_HISTORY ? next.slice(-MAX_HISTORY) : next;
      });
    },
    []
  );

  const addLines = useCallback(
    (entries) => {
      setLines((prev) => {
        const next = [...prev, ...entries];
        return next.length > MAX_HISTORY ? next.slice(-MAX_HISTORY) : next;
      });
    },
    []
  );

  // ── Command Executor ──
  const executeCommand = useCallback(
    async (raw) => {
      const trimmed = raw.trim();
      if (!trimmed) return;

      // Echo command
      addLine(`${PROMPT}${trimmed}`, '#94A3B8');

      const parts = trimmed.split(/\s+/);
      const cmd = parts[0].toLowerCase();
      const arg1 = parts[1]?.toLowerCase();

      switch (cmd) {
        case 'help':
          HELP_TEXT.split('\n').forEach((line) =>
            addLine(line, '#7dd3fc')
          );
          break;

        case 'clear':
          setLines([]);
          break;

        case 'status': {
          const active = agents.filter(
            (a) => a.current_status === 'RUNNING'
          ).length;
          const idle = agents.filter(
            (a) => a.current_status === 'IDLE'
          ).length;
          const activeG = goals.filter(
            (g) => g.status === 'ACTIVE'
          ).length;
          addLines([
            { text: '── Résumé Système ──', color: '#00F0FF' },
            {
              text: `  Agents: ${agents.length} total | ${active} running | ${idle} idle`,
              color: '#E2E8F0',
            },
            {
              text: `  Goals:  ${goals.length} total | ${activeG} actifs`,
              color: '#E2E8F0',
            },
            {
              text: `  Events: ${telemetry.length} événements récents`,
              color: '#E2E8F0',
            },
          ]);
          break;
        }

        case 'list': {
          if (arg1 === 'agents') {
            if (agents.length === 0) {
              addLine('  (aucun agent trouvé)', '#64748B');
              break;
            }
            addLine(
              `  ${'ID'.padEnd(10)} ${'NOM'.padEnd(28)} ${'RÔLE'.padEnd(20)} STATUS`,
              '#00F0FF'
            );
            addLine('  ' + '─'.repeat(74), '#1E293B');
            agents.forEach((a) => {
              const statusColor =
                a.current_status === 'RUNNING'
                  ? '#10B981'
                  : a.current_status === 'IDLE'
                  ? '#64748B'
                  : '#00F0FF';
              addLine(
                `  ${a.id.slice(0, 8).padEnd(10)} ${a.name
                  .slice(0, 26)
                  .padEnd(28)} ${(a.role || 'Worker')
                  .slice(0, 18)
                  .padEnd(20)} ${a.current_status}`,
                statusColor
              );
            });
          } else if (arg1 === 'goals') {
            if (goals.length === 0) {
              addLine('  (aucun objectif trouvé)', '#64748B');
              break;
            }
            addLine(
              `  ${'ID'.padEnd(10)} ${'AGENT'.padEnd(22)} ${'OBJECTIF'.padEnd(35)} STATUS`,
              '#A855F7'
            );
            addLine('  ' + '─'.repeat(78), '#1E293B');
            goals.forEach((g) => {
              addLine(
                `  ${g.id.slice(0, 8).padEnd(10)} ${(g.agent_name || 'Agent')
                  .slice(0, 20)
                  .padEnd(22)} ${g.objective.slice(0, 33).padEnd(35)} ${
                  g.status
                }`,
                g.status === 'ACTIVE' ? '#10B981' : '#64748B'
              );
            });
          } else {
            addLine(
              '  Usage: list agents | list goals',
              '#F59E0B'
            );
          }
          break;
        }

        case 'inspect': {
          const searchId = parts[1];
          if (!searchId) {
            addLine('  Usage: inspect <agent_id_prefix>', '#F59E0B');
            break;
          }
          const agent = agents.find((a) =>
            a.id.startsWith(searchId)
          );
          if (!agent) {
            addLine(`  Agent "${searchId}" non trouvé.`, '#F43F5E');
            break;
          }
          addLines([
            { text: `── Agent: ${agent.name} ──`, color: '#00F0FF' },
            { text: `  ID:       ${agent.id}`, color: '#E2E8F0' },
            { text: `  Rôle:     ${agent.role || 'Worker'}`, color: '#E2E8F0' },
            { text: `  Status:   ${agent.current_status}`, color: agent.current_status === 'RUNNING' ? '#10B981' : '#94A3B8' },
            { text: `  Autonomie: ${agent.default_autonomy_level}/5`, color: '#E2E8F0' },
            { text: `  Action:   ${agent.current_action || 'Aucune'}`, color: '#A855F7' },
            { text: `  Tâches:   ${agent.completed_tasks_count}/${agent.total_tasks_count}`, color: '#E2E8F0' },
            { text: `  Créé:     ${formatTimestamp(agent.created_at)}`, color: '#64748B' },
          ]);
          if (onSelectAgent) onSelectAgent(agent.id);
          break;
        }

        case 'logs': {
          const target = parts[1];
          let agent = null;
          if (target) {
            agent = agents.find(
              (a) => a.id.startsWith(target) || a.name.toLowerCase().includes(target.toLowerCase())
            );
          } else if (agents.length > 0) {
            agent = agents[0];
          }

          if (!agent) {
            addLine('  Usage: logs <agent_id_ou_nom> (ex: logs portfolio, logs rockib)', '#F59E0B');
            break;
          }

          addLine(`  🔍 Récupération des logs pour ${agent.name} (${agent.id.slice(0, 8)})...`, '#00F0FF');
          try {
            const resp = await authFetch(`/api/v1/agents/${agent.id}/logs?limit=15`);
            const data = resp.ok ? await resp.json() : { logs: [] };
            if (!data.logs || data.logs.length === 0) {
              addLine(`  (aucun log enregistré pour cet agent)`, '#64748B');
            } else {
              addLine(`  ── Journal d'Audit : ${data.agent_name} (${data.total_logs} entrées) ──`, '#00F0FF');
              data.logs.forEach((log) => {
                const timeStr = new Date(log.timestamp).toLocaleTimeString('fr-FR');
                const badgeColor =
                  log.level === 'ALLOW' || log.level === 'SUCCESS'
                    ? '#10B981'
                    : log.level === 'DENY' || log.level === 'CRITICAL'
                    ? '#F43F5E'
                    : log.level === 'ESCALATE' || log.level === 'WARNING'
                    ? '#F59E0B'
                    : '#00F0FF';
                addLine(`  [${timeStr}] [${log.type.toUpperCase()}] ${log.title}`, badgeColor);
                addLine(`    └─ ${log.summary}`, '#94A3B8');
              });
            }
          } catch (err) {
            addLine(`  ✗ Erreur de récupération: ${err.message}`, '#F43F5E');
          }
          break;
        }

        case 'wake': {
          const goalId = parts[1];
          if (!goalId) {
            addLine('  Usage: wake <goal_id_prefix>', '#F59E0B');
            break;
          }
          const goal = goals.find((g) => g.id.startsWith(goalId));
          if (!goal) {
            addLine(`  Goal "${goalId}" non trouvé.`, '#F43F5E');
            break;
          }
          addLine(`  ⚡ Déclenchement wake_goal sur ${goal.id.slice(0, 8)}...`, '#00F0FF');
          try {
            await onWakeGoal(goal.id);
            addLine('  ✓ Cycle d\'exécution terminé.', '#10B981');
          } catch (err) {
            addLine(`  ✗ Erreur: ${err.message}`, '#F43F5E');
          }
          break;
        }

        case 'spawn': {
          const name = parts.slice(1).join(' ').split('--')[0].trim();
          if (!name) {
            addLine(
              '  Usage: spawn <nom> [--role <rôle>] [--autonomy <0-5>]',
              '#F59E0B'
            );
            break;
          }
          let role = 'Worker Spécialisé';
          let autonomy = 2;
          const roleMatch = raw.match(/--role\s+([^\s-]+(?:\s+[^\s-]+)*?)(?:\s+--|$)/i);
          if (roleMatch) role = roleMatch[1].trim();
          const autMatch = raw.match(/--autonomy\s+(\d)/i);
          if (autMatch) autonomy = parseInt(autMatch[1], 10);

          addLine(`  🔧 Matérialisation de "${name}" (${role}, autonomie ${autonomy})...`, '#A855F7');
          try {
            await onSpawnAgent({
              name,
              role,
              default_autonomy_level: autonomy,
              parent_agent_id: null,
              mission: '',
            });
            addLine('  ✓ Agent déployé dans la matrice 3D.', '#10B981');
          } catch (err) {
            addLine(`  ✗ Erreur: ${err.message}`, '#F43F5E');
          }
          break;
        }

        case 'mission': {
          const objective = parts.slice(1).join(' ').trim();
          if (!objective) {
            addLine('  Usage: mission <description de la mission>', '#F59E0B');
            break;
          }
          if (agents.length === 0) {
            addLine('  ✗ Erreur: Aucun agent disponible pour recevoir la mission.', '#F43F5E');
            break;
          }
          
          const targetAgent = agents[0]; // On assigne au premier agent (l'Orchestrateur)
          addLine(`  🚀 Transmission de la mission à ${targetAgent.name}...`, '#A855F7');
          try {
            if (onCreateGoal) {
               const newGoal = await onCreateGoal(targetAgent.id, objective);
               addLine(`  ⚡ Mission créée [${newGoal?.id?.slice(0, 8) || 'OK'}]. Lancement du cycle d'arbitrage et d'exécution...`, '#00F0FF');
                if (onWakeGoal && newGoal?.id) {
                  let outcome = await onWakeGoal(newGoal.id);
                  for (let step = 0; step < 4; step++) {
                    const currentTasks = outcome?.details?.tasks || [];
                    const hasReady = currentTasks.some((t) => t.status === 'READY');
                    if (!hasReady) break;
                    outcome = await onWakeGoal(newGoal.id);
                  }
                  const taskList = outcome?.details?.tasks || [];
                  const withResults = taskList.filter((t) => t.result_summary);
                  if (withResults.length > 0) {
                    addLine('  \u2713 Mission ex\u00e9cut\u00e9e avec succ\u00e8s !', '#10B981');
                    for (const completed of withResults) {
                      const tag = completed.tool ? completed.tool.toUpperCase() : 'ACTION';
                      addLine('  ── [' + tag + '] ' + completed.description + ' ──', '#00F0FF');
                      completed.result_summary.split('\n').forEach((line) => {
                         if (line.trim()) {
                           const isLink = line.includes('/preview/') || line.startsWith('http');
                           addLine('  ' + line, isLink ? '#00F0FF' : '#E2E8F0');
                         }
                      });
                    }
                  } else {
                    const st = outcome?.result?.status || 'succès';
                    addLine('  \u2713 Cycle autonome termin\u00e9 (' + st + ').', '#10B981');
                  }
                } else {
                 addLine('  ✓ Mission acceptée et encodée dans la matrice. Le WakeRunner s\'en chargera.', '#10B981');
               }
            } else {
               addLine(`  ✗ Erreur: onCreateGoal n'est pas branché.`, '#F43F5E');
            }
          } catch (err) {
            addLine(`  ✗ Erreur: ${err.message}`, '#F43F5E');
          }
          break;
        }

        case 'telemetry': {
          if (telemetry.length === 0) {
            addLine('  (aucun événement récent)', '#64748B');
            break;
          }
          addLine('── Derniers événements ──', '#F59E0B');
          telemetry.slice(0, 10).forEach((t) => {
            const icon = t.type === 'decision' ? '🛡️' : '⚙️';
            addLine(
              `  ${icon} [${formatTimestamp(t.timestamp)}] ${t.agent_name}: ${t.summary.slice(0, 60)}`,
              t.type === 'decision' ? '#F59E0B' : '#10B981'
            );
          });
          break;
        }

        default: {
          if (agents.length === 0) {
            addLine(
              `  Commande inconnue: "${cmd}". Tapez "help" pour l'aide.`,
              '#F43F5E'
            );
            break;
          }
          
          const targetAgent = agents[0]; // Assigner au premier agent
          addLine(`  🚀 [Mission Implicite] Transmission à ${targetAgent.name}...`, '#A855F7');
          try {
            if (onCreateGoal) {
               await onCreateGoal(targetAgent.id, trimmed);
               addLine('  ✓ Mission acceptée et encodée dans la matrice. Le WakeRunner s\'en chargera.', '#10B981');
            } else {
               addLine(`  ✗ Erreur: onCreateGoal n'est pas branché.`, '#F43F5E');
            }
          } catch (err) {
            addLine(`  ✗ Erreur: ${err.message}`, '#F43F5E');
          }
          break;
        }
      }
    },
    [agents, goals, telemetry, onWakeGoal, onSpawnAgent, onSelectAgent, addLine, addLines]
  );

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      const cmd = input;
      setInput('');
      setCmdHistory((prev) => [cmd, ...prev].slice(0, 50));
      setHistoryIdx(-1);
      executeCommand(cmd);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (cmdHistory.length > 0) {
        const newIdx = Math.min(historyIdx + 1, cmdHistory.length - 1);
        setHistoryIdx(newIdx);
        setInput(cmdHistory[newIdx]);
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIdx > 0) {
        const newIdx = historyIdx - 1;
        setHistoryIdx(newIdx);
        setInput(cmdHistory[newIdx]);
      } else {
        setHistoryIdx(-1);
        setInput('');
      }
    }
  };

  if (!isOpen) return null;

  return (
    <div className="cyber-terminal glass-panel hud-interactive">
      {/* Terminal Header */}
      <div className="terminal-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Terminal size={16} color="var(--neon-emerald)" />
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              fontSize: '0.85rem',
              color: 'var(--neon-emerald)',
            }}
          >
            rockib-terminal
          </span>
          <span
            style={{
              fontSize: '0.65rem',
              color: 'var(--text-muted)',
              padding: '1px 6px',
              background: 'rgba(255,255,255,0.06)',
              borderRadius: '4px',
            }}
          >
            v1.0
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
            Ctrl+`
          </span>
          <button
            onClick={onClose}
            className="control-btn"
            style={{ padding: '3px', borderRadius: '50%' }}
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Terminal Output */}
      <div className="terminal-output" ref={scrollRef}>
        {lines.map((line, i) => (
          <div
            key={i}
            className="terminal-line"
            style={{ color: line.color }}
          >
            {line.text || '\u00A0'}
          </div>
        ))}
      </div>

      {/* Terminal Input */}
      <div className="terminal-input-row">
        <ChevronRight size={14} color="var(--neon-emerald)" />
        <span
          className="mono"
          style={{ color: 'var(--neon-cyan)', fontSize: '0.8rem' }}
        >
          {PROMPT}
        </span>
        <input
          ref={inputRef}
          type="text"
          className="terminal-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          spellCheck={false}
          autoComplete="off"
        />
      </div>
    </div>
  );
}
