import { useState, useEffect } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import type { Settings } from './types';
import Header from './components/Header';
import StatsCards from './components/StatsCards';
import BalanceTable from './components/BalanceTable';
import PriceGrid from './components/PriceGrid';
import TradesTable from './components/TradesTable';
import TransfersTable from './components/TransfersTable';
import SymbolRankings from './components/SymbolRankings';
import RotationLog from './components/RotationLog';
import RankingPage from './components/RankingPage';
import SettingsPage from './components/SettingsPage';
import LoginPage from './components/LoginPage';
import LogsPage from './components/LogsPage';
import DemoComparison from './components/DemoComparison';

export default function App() {
  const {
    state, connected, authenticated, authError,
    attemptsRemaining, blocked, retryAfter, authLoading,
    captchaRequired, captchaSiteKey, ipDenied,
    login, logout, send, sendWithCallback,
  } = useWebSocket();
  const [activeTab, setActiveTab] = useState<'dashboard' | 'ranking' | 'settings' | 'logs'>('dashboard');
  const [showConnectingText, setShowConnectingText] = useState(false);

  // Delay showing "Connecting..." text so IP-denied users see only a spinner
  // before the denied page appears (auth_denied arrives within ~200ms)
  useEffect(() => {
    if (!connected && !blocked && !ipDenied) {
      const timer = setTimeout(() => setShowConnectingText(true), 1500);
      return () => clearTimeout(timer);
    } else {
      setShowConnectingText(false);
    }
  }, [connected, blocked, ipDenied]);

  // IP denied — dead end, no login, no reconnect
  if (ipDenied) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-slate-500 text-lg">You are not allowed here.</p>
      </div>
    );
  }

  // Not connected
  if (!connected && !blocked) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          {showConnectingText && (
            <>
              <p className="text-slate-400 text-lg">Connecting to CoirnaBot...</p>
              <p className="text-slate-500 text-sm mt-2">Make sure <code className="text-slate-400">python run.py</code> is running</p>
            </>
          )}
        </div>
      </div>
    );
  }

  // Not authenticated
  if (!authenticated) {
    return (
      <LoginPage
        onLogin={login}
        error={authError}
        attemptsRemaining={attemptsRemaining}
        blocked={blocked}
        retryAfter={retryAfter}
        loading={authLoading}
        captchaRequired={captchaRequired}
        captchaSiteKey={captchaSiteKey}
      />
    );
  }

  // Waiting for first state
  if (!state) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-slate-400 text-lg">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  const symbols = Object.keys(state.balances).length > 0
    ? Object.keys(Object.values(state.balances)[0].crypto)
    : [];

  const handleSaveSettings = (settings: Settings) => {
    send({ type: 'save_settings', settings });
  };

  const handleApplySettings = (settings: Settings) => {
    send({ type: 'apply_settings', settings });
  };

  return (
    <div className="min-h-screen flex flex-col">
      <Header
        connected={connected}
        uptimeSeconds={state.uptime_seconds}
        connectedExchanges={state.connected_exchanges}
        totalExchanges={state.total_exchanges}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        portfolio={state.portfolio}
        simulation={state.simulation}
        profitStats={state.profit_stats ?? null}
        onLogout={logout}
      />

      <main className="flex-1 p-3 sm:p-6 pb-20 sm:pb-20 md:pb-6 max-w-[1600px] mx-auto w-full">
        {activeTab === 'dashboard' ? (
          <div className="space-y-3 sm:space-y-5">
            {state.optimizer?.discovery_mode && (
              <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 text-center">
                <p className="text-amber-300 font-medium">
                  Discovery Stage: scoring all symbols on all exchanges
                </p>
                <p className="text-amber-400/80 text-sm mt-1">
                  {Math.ceil(state.optimizer.discovery_remaining)}s remaining — trading starts after discovery
                </p>
              </div>
            )}

            <StatsCards portfolio={state.portfolio} simulation={state.simulation} profitStats={state.profit_stats ?? { net_profit: 0, hourly_net: 0, session_hourly_rate: 0, trading_pnl: 0, transfer_fees: 0, is_profitable: false }} demoComparison={state.demo_comparison} uptimeSeconds={state.uptime_seconds} />

            {state.optimizer?.rankings?.length > 0 && (
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 sm:gap-5">
                <div className="xl:col-span-2">
                  <SymbolRankings
                    rankings={state.optimizer.rankings.slice(0, 20)}
                    warmupRemaining={state.optimizer.warmup_remaining}
                    autoRotate={state.optimizer.auto_rotate}
                    discoveryMode={state.optimizer.discovery_mode}
                  />
                </div>
                <RotationLog rotations={state.optimizer.rotations} />
              </div>
            )}

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 sm:gap-5">
              <BalanceTable balances={state.balances} symbols={symbols} />
              <PriceGrid prices={state.prices} />
            </div>

            {state.demo_comparison?.enabled && (
              <DemoComparison data={state.demo_comparison} />
            )}

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 sm:gap-5">
              <TradesTable trades={state.recent_trades} totalPnl={state.portfolio.trading_pnl} />
              <TransfersTable transfers={state.recent_transfers} totalFees={state.portfolio.transfer_fees} />
            </div>

            <div className="text-center text-[10px] sm:text-xs text-slate-600 py-2">
              Portfolio: ${state.portfolio.initial_investment.toFixed(0)} initial
              {' | '}Trading: {state.portfolio.trading_pnl >= 0 ? '+' : ''}{state.portfolio.trading_pnl.toFixed(4)}
              {' | '}Fees: -{state.portfolio.transfer_fees.toFixed(4)}
              {' | '}Price movement: {state.portfolio.price_pnl >= 0 ? '+' : ''}{state.portfolio.price_pnl.toFixed(2)}
            </div>
          </div>
        ) : activeTab === 'ranking' ? (
          <RankingPage
            optimizer={state.optimizer}
            tickCount={state.optimizer?.tick_count ?? 0}
            portfolio={state.portfolio}
            simulation={state.simulation}
            allTrades={state.all_trades}
            allTransfers={state.all_transfers}
            allConfigHistory={state.all_config_history}
          />
        ) : activeTab === 'settings' ? (
          <SettingsPage
            currentSettings={state.settings}
            onSave={handleSaveSettings}
            onApply={handleApplySettings}
            onSendMessage={send}
          />
        ) : (
          <LogsPage
            botLogs={state.bot_logs ?? []}
            authLogs={state.auth_logs ?? []}
            sendWithCallback={sendWithCallback}
            uptimeSeconds={state.uptime_seconds}
          />
        )}
      </main>
    </div>
  );
}
