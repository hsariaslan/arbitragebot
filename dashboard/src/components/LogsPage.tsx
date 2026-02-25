import { useState } from 'react';
import type { BotLogEntry, AuthLogEntry } from '../types';
import BotLogsTab from './BotLogsTab';
import AuthLogPage from './AuthLogPage';

interface LogsPageProps {
  botLogs: BotLogEntry[];
  authLogs: AuthLogEntry[];
  sendWithCallback: (msg: object, callback: (data: any) => void) => void;
  uptimeSeconds: number;
}

export default function LogsPage({ botLogs, authLogs, sendWithCallback, uptimeSeconds }: LogsPageProps) {
  const [activeSubTab, setActiveSubTab] = useState<'bot' | 'auth'>('bot');

  return (
    <div className="space-y-4">
      {/* Sub-tab navigation */}
      <div className="flex items-center gap-1 border-b border-slate-700 overflow-x-auto">
        <button
          onClick={() => setActiveSubTab('bot')}
          className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
            activeSubTab === 'bot'
              ? 'border-blue-500 text-white'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Bot Logs
        </button>
        <button
          onClick={() => setActiveSubTab('auth')}
          className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
            activeSubTab === 'auth'
              ? 'border-blue-500 text-white'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Auth Logs
        </button>
      </div>

      {/* Sub-tab content */}
      {activeSubTab === 'bot' ? (
        <BotLogsTab logs={botLogs} sendWithCallback={sendWithCallback} uptimeSeconds={uptimeSeconds} />
      ) : (
        <AuthLogPage authLogs={authLogs} sendWithCallback={sendWithCallback} uptimeSeconds={uptimeSeconds} />
      )}
    </div>
  );
}
