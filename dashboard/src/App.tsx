import { useState, useEffect } from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useWebSocket } from './hooks/useWebSocket';
import type { Settings, DashboardState } from './types';
import Header from './components/Header';
import StatsCards from './components/StatsCards';
import BalanceTable from './components/BalanceTable';
import PriceGrid from './components/PriceGrid';
import TradesTable from './components/TradesTable';
import TransfersTable from './components/TransfersTable';
import SymbolRankings from './components/SymbolRankings';
import HedgesPanel from './components/HedgesPanel';
import RotationLog from './components/RotationLog';
import RankingPage from './components/RankingPage';
import SettingsPage from './components/SettingsPage';
import LoginPage from './components/LoginPage';
import LogsPage from './components/LogsPage';
import DemoComparison from './components/DemoComparison';

function DashboardPage({ state }: { state: DashboardState }) {
  const balanceEntries = Object.values(state.balances);
  const symbols = balanceEntries.length > 0
    ? Object.keys(balanceEntries[0].crypto)
    : [];

  return (
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

      <StatsCards portfolio={state.portfolio} simulation={state.simulation} profitStats={state.profit_stats ?? { net_profit: 0, hourly_net: 0, session_hourly_rate: 0, trading_pnl: 0, transfer_fees: 0, credited_cashback: 0, pending_cashback: 0, is_profitable: false, referrer_earnings_total: 0 }} demoComparison={state.demo_comparison} uptimeSeconds={state.uptime_seconds} />

      {state.optimizer?.rankings?.length > 0 && (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 sm:gap-5">
          <div className="xl:col-span-2">
            <SymbolRankings
              rankings={state.optimizer.rankings.slice(0, 20)}
              warmupRemaining={state.optimizer.warmup_remaining}
              autoRotate={state.optimizer.auto_rotate}
              discoveryMode={state.optimizer.discovery_mode}
              fundingRates={state.funding_rates}
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

      <HedgesPanel hedges={state.hedges} />

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
  );
}

export default function App() {
  const {
    state, connected, authenticated, authError,
    attemptsRemaining, blocked, retryAfter, authLoading,
    captchaRequired, captchaSiteKey, ipDenied, wsInitialized,
    login, logout, send, sendWithCallback,
  } = useWebSocket();
  const [showConnectingText, setShowConnectingText] = useState(false);
  // Track whether user has ever been authenticated this session
  const [everAuthenticated, setEverAuthenticated] = useState(false);

  useEffect(() => {
    if (authenticated) setEverAuthenticated(true);
  }, [authenticated]);

  // Delay showing "Connecting..." text so IP-denied users see only a spinner
  // before the denied page appears (auth_denied arrives within ~200ms)
  useEffect(() => {
    if (!connected && !blocked && !ipDenied && !everAuthenticated) {
      const timer = setTimeout(() => setShowConnectingText(true), 1500);
      return () => clearTimeout(timer);
    } else {
      setShowConnectingText(false);
    }
  }, [connected, blocked, ipDenied, everAuthenticated]);

  // IP denied — top priority, dead end, no login, no reconnect, nothing else in DOM
  if (ipDenied) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-slate-500 text-lg">You are not allowed here.</p>
      </div>
    );
  }

  // Before first auth message arrives: render nothing (blank screen)
  // This ensures denied IPs never see any loading UI — just blank → denied page
  if (!wsInitialized && !everAuthenticated) {
    return <div className="min-h-screen" />;
  }

  // Show connecting screen ONLY on initial load (never authenticated before)
  if (!connected && !blocked && !everAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          {showConnectingText && (
            <>
              <p className="text-slate-400 text-lg">Connecting to ArbitrageBot...</p>
              <p className="text-slate-500 text-sm mt-2">Make sure <code className="text-slate-400">python run.py</code> is running</p>
            </>
          )}
        </div>
      </div>
    );
  }

  // Not authenticated (and never was — show login)
  if (!authenticated && !everAuthenticated) {
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

  // Waiting for first state (no stale data yet)
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

  const handleSaveSettings = (settings: Settings) => {
    send({ type: 'save_settings', settings });
  };

  const handleApplySettings = (settings: Settings) => {
    send({ type: 'apply_settings', settings });
  };

  return (
    <HashRouter>
      <div className="min-h-screen flex flex-col">
        <Header
          connected={connected}
          uptimeSeconds={state.uptime_seconds}
          uptimeInfo={state.uptime_info}
          connectedExchanges={state.connected_exchanges}
          totalExchanges={state.total_exchanges}
          proxyUptimeInfo={state.proxy_uptime_info}
          portfolio={state.portfolio}
          simulation={state.simulation}
          profitStats={state.profit_stats ?? null}
          anomalyProtection={state.anomaly_protection}
          manualStopped={state.manual_stopped}
          manualStopTimestamp={state.manual_stop_timestamp}
          hedges={state.hedges}
          onLogout={logout}
        />

        <main className="flex-1 p-3 sm:p-6 pb-20 sm:pb-20 md:pb-6 w-full">
          <Routes>
            <Route path="/" element={
              <DashboardPage state={state} />
            } />
            <Route path="/rankings" element={
              <RankingPage
                optimizer={state.optimizer}
                tickCount={state.optimizer?.tick_count ?? 0}
                portfolio={state.portfolio}
                simulation={state.simulation}
                allTrades={state.all_trades}
                allTransfers={state.all_transfers}
                allConfigHistory={state.all_config_history}
                demoDiscrepancies={state.demo_comparison?.recent_discrepancies}
                feeConfigs={state.fee_configs}
                transferConfigs={state.transfer_configs}
                profitStats={state.profit_stats}
                hourlyPnl={state.hourly_pnl}
                dailyPnl={state.daily_pnl}
                hedges={state.hedges}
                fundingRates={state.funding_rates}
              />
            } />
            <Route path="/rankings/historical" element={
              <RankingPage
                optimizer={state.optimizer}
                tickCount={state.optimizer?.tick_count ?? 0}
                portfolio={state.portfolio}
                simulation={state.simulation}
                allTrades={state.all_trades}
                allTransfers={state.all_transfers}
                allConfigHistory={state.all_config_history}
                demoDiscrepancies={state.demo_comparison?.recent_discrepancies}
                feeConfigs={state.fee_configs}
                transferConfigs={state.transfer_configs}
                profitStats={state.profit_stats}
                hourlyPnl={state.hourly_pnl}
                dailyPnl={state.daily_pnl}
                hedges={state.hedges}
                fundingRates={state.funding_rates}
                defaultView="historical"
              />
            } />
            <Route path="/settings" element={
              <SettingsPage
                currentSettings={state.settings}
                onSave={handleSaveSettings}
                onApply={handleApplySettings}
                onSendMessage={send}
                onSendWithCallback={sendWithCallback}
                feeConfigs={state.fee_configs}
                feeRealMode={state.fee_real_mode}
                feeStats={state.fee_stats}
                transferConfigs={state.transfer_configs}
                anomalyProtection={state.anomaly_protection}
                manualStopped={state.manual_stopped}
                balances={state.balances}
                distributeEnabled={state.distribute_enabled}
              />
            } />
            <Route path="/settings/:subTab" element={
              <SettingsPage
                currentSettings={state.settings}
                onSave={handleSaveSettings}
                onApply={handleApplySettings}
                onSendMessage={send}
                onSendWithCallback={sendWithCallback}
                feeConfigs={state.fee_configs}
                feeRealMode={state.fee_real_mode}
                feeStats={state.fee_stats}
                transferConfigs={state.transfer_configs}
                anomalyProtection={state.anomaly_protection}
                manualStopped={state.manual_stopped}
                balances={state.balances}
                distributeEnabled={state.distribute_enabled}
              />
            } />
            <Route path="/logs" element={
              <LogsPage
                botLogs={state.bot_logs ?? []}
                botLogsTotal={state.bot_logs_total ?? 0}
                authLogs={state.auth_logs ?? []}
                sendWithCallback={sendWithCallback}
                uptimeSeconds={state.uptime_seconds}
              />
            } />
            <Route path="/logs/:subTab" element={
              <LogsPage
                botLogs={state.bot_logs ?? []}
                botLogsTotal={state.bot_logs_total ?? 0}
                authLogs={state.auth_logs ?? []}
                sendWithCallback={sendWithCallback}
                uptimeSeconds={state.uptime_seconds}
              />
            } />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </HashRouter>
  );
}
