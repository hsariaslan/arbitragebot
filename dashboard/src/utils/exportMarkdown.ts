import type { OptimizerState, Portfolio, Simulation, ProfitStats, Trade, Transfer, ConfigSnapshot } from '../types';

function fmt(n: number, decimals = 2): string {
  return n.toFixed(decimals);
}

function fmtTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toISOString().replace('T', ' ').replace(/\.\d+Z$/, '') + ' UTC';
}

function fmtDuration(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function mdTable(headers: string[], rows: string[][]): string {
  const sep = headers.map(() => '---');
  const lines = [
    '| ' + headers.join(' | ') + ' |',
    '| ' + sep.join(' | ') + ' |',
    ...rows.map(r => '| ' + r.join(' | ') + ' |'),
  ];
  return lines.join('\n');
}

export function exportRankingsMarkdown(data: {
  optimizer: OptimizerState;
  portfolio?: Portfolio | null;
  simulation?: Simulation | null;
  profitStats?: ProfitStats | null;
  allTrades?: Trade[];
  allTransfers?: Transfer[];
  allConfigHistory?: ConfigSnapshot[];
  uptimeSeconds?: number;
}): string {
  const { optimizer, portfolio, simulation, profitStats, allTrades, allTransfers, uptimeSeconds } = data;
  const sections: string[] = [];

  // --- Session Summary ---
  sections.push('## Session Summary\n');
  const summaryRows: string[] = [];
  if (uptimeSeconds) summaryRows.push(`- **Uptime**: ${fmtDuration(uptimeSeconds)}`);
  summaryRows.push(`- **Active Symbols**: ${optimizer.active_symbols?.length ?? 0} (${optimizer.min_active_symbols ?? 0}-${optimizer.max_active_symbols ?? 0})`);
  summaryRows.push(`- **Total Ticks**: ${optimizer.tick_count?.toLocaleString() ?? 0}`);
  if (portfolio) {
    summaryRows.push(`- **Portfolio Value**: $${fmt(portfolio.total_value)}`);
    summaryRows.push(`- **Initial Investment**: $${fmt(portfolio.initial_investment)}`);
    summaryRows.push(`- **Trading P&L**: $${fmt(portfolio.trading_pnl, 4)}`);
    summaryRows.push(`- **Transfer Fees**: -$${fmt(Math.abs(portfolio.transfer_fees), 4)}`);
    summaryRows.push(`- **Price P&L**: $${fmt(portfolio.price_pnl)}`);
  }
  if (profitStats) {
    summaryRows.push(`- **Net Profit**: $${fmt(profitStats.net_profit, 4)}`);
    summaryRows.push(`- **Session $/hr**: $${fmt(profitStats.session_hourly_rate, 4)}`);
    summaryRows.push(`- **Credited Cashback**: $${fmt(profitStats.credited_cashback, 4)}`);
    summaryRows.push(`- **Pending Cashback**: $${fmt(profitStats.pending_cashback, 4)}`);
  }
  if (simulation) {
    summaryRows.push(`- **Total Trades**: ${simulation.total_trades.toLocaleString()}`);
    summaryRows.push(`- **Trades/min**: ${simulation.trades_per_minute}`);
    summaryRows.push(`- **Transfers**: ${simulation.total_transfers}`);
    summaryRows.push(`- **Skipped**: ${simulation.skipped_trades}`);
  }
  sections.push(summaryRows.join('\n'));

  // --- Rolling Rankings ---
  if (optimizer.rankings?.length > 0) {
    sections.push('\n## Rolling Rankings\n');
    const headers = ['#', 'Symbol', 'Score', 'Freq%', 'Net%', 'Best%', 'ProfTicks', 'Est$/hr', 'Mult', 'Trade$', 'Status', 'Exchanges'];
    const rows = optimizer.rankings.map((r, i) => [
      String(i + 1),
      r.symbol.replace('USDT', ''),
      r.score > 0 ? r.score.toFixed(4) : r.total_ticks > 0 ? '0' : '-',
      r.total_ticks > 0 ? (r.frequency * 100).toFixed(1) + '%' : '-',
      r.total_ticks > 0 ? r.avg_net_pct.toFixed(4) + '%' : '-',
      r.total_ticks > 0 ? r.best_net_pct.toFixed(4) + '%' : '-',
      r.profitable_ticks > 0 ? String(r.profitable_ticks) : '-',
      r.est_hourly_profit > 0 ? '$' + r.est_hourly_profit.toFixed(4) : '-',
      r.is_active ? r.trade_multiplier.toFixed(2) + 'x' : '-',
      r.is_active ? '$' + r.allocated_trade_size.toFixed(0) : '-',
      r.is_active ? 'ACTIVE' : r.score > 0 ? 'candidate' : r.total_ticks > 0 ? 'avoid' : '',
      (r.dominant_buyers?.length ? r.dominant_buyers.join('/') + '->' + (r.dominant_sellers?.join('/') ?? '') : '-'),
    ]);
    sections.push(mdTable(headers, rows));
  }

  // --- Historical Rankings ---
  if (optimizer.historical_rankings?.length > 0) {
    sections.push('\n## Historical Rankings\n');
    const headers = ['Symbol', 'Score', 'Trend', 'ProfTicks', 'Freq%', 'StrTimes', 'StrDur', 'VStrTimes', 'VStrDur'];
    const rows = optimizer.historical_rankings.map(r => [
      r.symbol.replace('USDT', ''),
      r.all_time_score.toFixed(4),
      r.trend > 0 ? 'UP' : r.trend < 0 ? 'DOWN' : 'STABLE',
      String(r.total_profitable_ticks),
      (r.overall_frequency * 100).toFixed(1) + '%',
      String(r.times_became_strong ?? 0),
      fmtDuration(r.total_strong_duration ?? 0),
      String(r.times_became_very_strong ?? 0),
      fmtDuration(r.total_very_strong_duration ?? 0),
    ]);
    sections.push(mdTable(headers, rows));
  }

  // --- Exchange Rankings ---
  if (optimizer.exchange_rankings?.length > 0) {
    sections.push('\n## Exchange Rankings\n');
    const headers = ['Exchange', 'Fee%', 'Buy', 'Sell', 'Total', 'Profit'];
    const rows = optimizer.exchange_rankings.map(ex => [
      ex.exchange,
      ex.fee_pct + '%',
      String(ex.as_buyer),
      String(ex.as_seller),
      String(ex.total_involvement),
      ex.profit_sum > 0 ? '$' + ex.profit_sum.toFixed(2) : '0',
    ]);
    sections.push(mdTable(headers, rows));
  }

  // --- Top Symbols (Rolling) ---
  if (optimizer.rankings?.length > 0) {
    const top = [...optimizer.rankings]
      .filter((r: any) => r.est_hourly_profit > 0)
      .sort((a: any, b: any) => b.est_hourly_profit - a.est_hourly_profit)
      .slice(0, 10);
    if (top.length > 0) {
      sections.push('\n## Top Symbols (Rolling — current scoring window)\n');
      const headers = ['#', 'Symbol', 'Active', '$/hr', 'Avg Net%', 'Freq%', 'Tier'];
      const rows = top.map((r: any, i: number) => [
        String(i + 1),
        r.symbol,
        r.is_active ? '✓' : '·',
        '$' + r.est_hourly_profit.toFixed(4),
        r.avg_profitable_net.toFixed(4) + '%',
        (r.frequency * 100).toFixed(1) + '%',
        r.focus_tier,
      ]);
      sections.push(mdTable(headers, rows));
    }
  }

  // --- Top Symbols (Historical) ---
  if (optimizer.historical_rankings?.length > 0) {
    const topHist = [...optimizer.historical_rankings]
      .filter((s: any) => s.est_total_profit > 0)
      .sort((a: any, b: any) => b.est_total_profit - a.est_total_profit)
      .slice(0, 10);
    if (topHist.length > 0) {
      sections.push('\n## Top Symbols (Historical — cumulative session)\n');
      const headers = ['#', 'Symbol', 'Active', 'Total $', '$/hr', 'Avg Net%', 'Ticks', 'Activations', 'Demotions'];
      const rows = topHist.map((s: any, i: number) => [
        String(i + 1),
        s.symbol,
        s.is_active ? '✓' : '·',
        '$' + s.est_total_profit.toFixed(2),
        '$' + s.est_hourly_rate.toFixed(4),
        s.avg_net_pct.toFixed(4) + '%',
        String(s.total_ticks),
        String(s.times_activated),
        String(s.times_demoted),
      ]);
      sections.push(mdTable(headers, rows));
    }
  }

  // --- Top Symbol × Exchange-Pair (from executed trades) ---
  if (allTrades && allTrades.length > 0) {
    const buckets = new Map<string, { symbol: string; buy: string; sell: string; trades: number; profit: number; volumeUsd: number }>();
    for (const t of allTrades) {
      const key = `${t.symbol}|${t.buy_exchange}|${t.sell_exchange}`;
      const cur = buckets.get(key);
      if (cur) {
        cur.trades += 1;
        cur.profit += t.profit_usd;
        cur.volumeUsd += t.trade_amount;
      } else {
        buckets.set(key, { symbol: t.symbol, buy: t.buy_exchange, sell: t.sell_exchange, trades: 1, profit: t.profit_usd, volumeUsd: t.trade_amount });
      }
    }
    const top = [...buckets.values()].sort((a, b) => b.profit - a.profit).slice(0, 15);
    if (top.length > 0) {
      sections.push('\n## Top Symbol × Exchange-Pair Combos by Profit\n');
      const headers = ['#', 'Symbol', 'Route', 'Trades', 'Total $', 'Avg $/trade', 'Volume $'];
      const rows = top.map((b, i) => [
        String(i + 1),
        b.symbol.replace('USDT', ''),
        `${b.buy}→${b.sell}`,
        String(b.trades),
        '$' + b.profit.toFixed(4),
        '$' + (b.profit / b.trades).toFixed(4),
        '$' + b.volumeUsd.toFixed(2),
      ]);
      sections.push(mdTable(headers, rows));
    }
  }

  // --- Recent Trades ---
  if (allTrades && allTrades.length > 0) {
    sections.push('\n## Recent Trades (last 50)\n');
    const recentTrades = allTrades.slice(-50).reverse();
    const headers = ['Time', 'Symbol', 'Buy@', 'Sell@', 'Spread%', 'Net%', 'Profit'];
    const rows = recentTrades.map(t => [
      fmtTime(t.timestamp),
      t.symbol.replace('USDT', ''),
      t.buy_exchange,
      t.sell_exchange,
      t.spread_pct.toFixed(4) + '%',
      t.net_pct.toFixed(4) + '%',
      (t.profit_usd >= 0 ? '+' : '') + '$' + t.profit_usd.toFixed(4),
    ]);
    sections.push(mdTable(headers, rows));
  }

  // --- Recent Transfers ---
  if (allTransfers && allTransfers.length > 0) {
    sections.push('\n## Recent Transfers (last 20)\n');
    const recentTransfers = allTransfers.slice(-20).reverse();
    const headers = ['Time', 'Type', 'From', 'To', 'Symbol', 'Amount', 'Fee'];
    const rows = recentTransfers.map(t => [
      fmtTime(t.timestamp),
      t.type,
      t.from_exchange,
      t.to_exchange,
      t.symbol,
      '$' + t.amount_usd.toFixed(2),
      '$' + t.fee_usd.toFixed(4),
    ]);
    sections.push(mdTable(headers, rows));
  }

  return `# ArbitrageBot Rankings Export\n_Generated: ${new Date().toISOString().replace('T', ' ').replace(/\.\d+Z$/, '')} UTC_\n\n` + sections.join('\n');
}
