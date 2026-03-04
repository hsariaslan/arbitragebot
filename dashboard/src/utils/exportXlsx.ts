import * as XLSX from 'xlsx';
import type { ConfigSnapshot, DailyPnlEntry, DemoDiscrepancy, ExchangeFeeConfig, ExchangeTransferConfig, HourlyPnlEntry, OptimizerState, Portfolio, ProfitStats, Simulation, Trade, Transfer } from '../types';

const tier1 = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'BNBUSDT', 'DOGEUSDT', 'ADAUSDT'];
const tier2 = ['AVAXUSDT', 'LINKUSDT', 'POLUSDT', 'DOTUSDT', 'NEARUSDT', 'SUIUSDT', 'APTUSDT', 'TRXUSDT'];
const tier3 = ['ARBUSDT', 'OPUSDT', 'FILUSDT', 'ATOMUSDT', 'INJUSDT'];
const getTier = (sym: string) => tier1.includes(sym) ? 'T1' : tier2.includes(sym) ? 'T2' : tier3.includes(sym) ? 'T3' : 'T4';

export function exportXlsx(
  optimizer: OptimizerState,
  portfolio: Portfolio | null,
  simulation: Simulation | null,
  allTrades: Trade[] = [],
  allTransfers: Transfer[] = [],
  allConfigHistory: ConfigSnapshot[] = [],
  demoDiscrepancies: DemoDiscrepancy[] = [],
  feeConfigs?: Record<string, ExchangeFeeConfig>,
  transferConfigs?: Record<string, ExchangeTransferConfig>,
  profitStats?: ProfitStats | null,
  hourlyPnl?: HourlyPnlEntry[],
  dailyPnl?: DailyPnlEntry[],
) {
  const wb = XLSX.utils.book_new();
  const now = new Date();
  const sessionDuration = optimizer.session_start ? (Date.now() / 1000 - optimizer.session_start) : 0;

  // -- Lifecycle funnel stats (for Summary) --
  const hist = optimizer.historical_rankings || [];
  const totalSymbols = hist.length;
  const totalCandidates = hist.filter(h => h.times_became_candidate > 0).length;
  const totalWatchlisted = hist.filter(h => h.times_entered_watchlist > 0).length;
  const totalConfirmed = hist.filter(h => h.times_confirmed > 0).length;
  const totalActivated = hist.filter(h => h.times_activated > 0).length;
  const totalStrong = hist.filter(h => h.times_became_strong > 0).length;
  const totalVeryStrong = hist.filter(h => h.times_became_very_strong > 0).length;

  // 1. Summary sheet
  const summaryData = [
    ['CoirnaBot Rankings Export'],
    ['Generated', now.toISOString()],
    ['Session Duration (s)', Math.round(sessionDuration)],
    ['Active Symbols', optimizer.active_symbols?.join(', ') ?? ''],
    ['Min Active', optimizer.min_active_symbols ?? ''],
    ['Max Active', optimizer.max_active_symbols ?? ''],
    ['Scoring Window (s)', optimizer.scoring_window],
    ['Eval Interval (s)', optimizer.evaluation_interval],
    ['Tick Count', optimizer.tick_count],
    [],
    ['Portfolio'],
    ['Total Value', portfolio?.total_value ?? ''],
    ['Initial Investment', portfolio?.initial_investment ?? ''],
    ['Net P&L', portfolio?.net_pnl ?? ''],
    ['Trading P&L', portfolio?.trading_pnl ?? ''],
    ['Transfer Fees', portfolio?.transfer_fees ?? ''],
    ['Price P&L', portfolio?.price_pnl ?? ''],
    [],
    ['Simulation'],
    ['Total Trades', simulation?.total_trades ?? ''],
    ['Skipped Trades', simulation?.skipped_trades ?? ''],
    ['Low Profit Skips', simulation?.low_profit_skips ?? ''],
    ['Total Transfers', simulation?.total_transfers ?? ''],
    ['Trades/min', simulation?.trades_per_minute ?? ''],
    [],
    ['Profitability'],
    ['Trading Profit $', portfolio?.trading_pnl ?? ''],
    ['Transfer Fees $', portfolio?.transfer_fees ?? ''],
    ['Credited Cashback $', profitStats?.credited_cashback ?? ''],
    ['Pending Cashback $', profitStats?.pending_cashback ?? ''],
    ['Referrer Earnings $', profitStats?.referrer_earnings_total ?? ''],
    ['Net Trading P&L $', portfolio && profitStats ? (portfolio.trading_pnl - portfolio.transfer_fees + (profitStats.credited_cashback ?? 0)) : (portfolio ? (portfolio.trading_pnl - portfolio.transfer_fees) : '')],
    ['Fee/Profit Ratio', portfolio && portfolio.trading_pnl > 0 ? (portfolio.transfer_fees / portfolio.trading_pnl * 100).toFixed(1) + '%' : ''],
    ['Net $/hr', profitStats?.session_hourly_rate ?? ''],
    [],
    ['Lifecycle Funnel'],
    ['Total Symbols', totalSymbols],
    ['Became Candidate', totalCandidates],
    ['Watchlisted', totalWatchlisted],
    ['Confirmed', totalConfirmed],
    ['Activated', totalActivated],
    ['Became Strong', totalStrong],
    ['Became Very Strong', totalVeryStrong],
  ];
  const wsSummary = XLSX.utils.aoa_to_sheet(summaryData);
  XLSX.utils.book_append_sheet(wb, wsSummary, 'Summary');

  // 2. Symbol Rankings (Rolling)
  if (optimizer.rankings?.length > 0) {
    const rollingRows = optimizer.rankings.map((r, i) => ({
      '#': i + 1,
      Symbol: r.symbol.replace('USDT', ''),
      Tier: getTier(r.symbol),
      Score: r.score,
      Frequency: r.frequency,
      'Avg Net%': r.avg_net_pct,
      'Avg Profitable Net%': r.avg_profitable_net,
      'Best Net%': r.best_net_pct,
      'Profitable Ticks': r.profitable_ticks,
      'Total Ticks': r.total_ticks,
      'Est $/hr': r.est_hourly_profit,
      'Trade Mult': r.trade_multiplier,
      'Allocated Trade $': r.allocated_trade_size,
      'Focus Tier': r.focus_tier ?? '',
      'Dominant Buyers': r.dominant_buyers?.join(', ') ?? '',
      'Dominant Sellers': r.dominant_sellers?.join(', ') ?? '',
      'Cur Net%': r.current_net_pct ?? '',
      Active: r.is_active ? 'YES' : '',
    }));
    const wsRolling = XLSX.utils.json_to_sheet(rollingRows);
    XLSX.utils.book_append_sheet(wb, wsRolling, 'Rolling Rankings');
  }

  // 3. Symbol Rankings (Historical)
  if (optimizer.historical_rankings?.length > 0) {
    const histRows = optimizer.historical_rankings.map((h, i) => ({
      '#': i + 1,
      Symbol: h.symbol.replace('USDT', ''),
      Tier: getTier(h.symbol),
      'All-Time Score': h.all_time_score,
      'Rolling Score': h.rolling_score,
      Trend: h.trend,
      'Total Profitable Ticks': h.total_profitable_ticks,
      'Total Ticks': h.total_ticks,
      'Overall Frequency': h.overall_frequency,
      'Avg Net%': h.avg_net_pct,
      'Avg Profitable Net%': h.avg_profitable_net,
      'Best Net%': h.best_net_pct,
      'Worst Net%': h.worst_net_pct,
      'Est Total Profit $': h.est_total_profit,
      'Est $/hr': h.est_hourly_rate,
      'Longest Profitable Streak': h.longest_profitable_streak,
      'Longest Unprofitable Streak': h.longest_unprofitable_streak,
      'Times Candidate': h.times_became_candidate,
      'Times Watchlisted': h.times_entered_watchlist,
      'Times Confirmed': h.times_confirmed,
      'Times Activated': h.times_activated,
      'Times Demoted': h.times_demoted,
      'Times Strong': h.times_became_strong,
      'Strong Duration (s)': h.total_strong_duration,
      'Times Very Strong': h.times_became_very_strong,
      'Very Strong Duration (s)': h.total_very_strong_duration,
      'Active Duration (s)': h.total_active_duration,
      Active: h.is_active ? 'YES' : '',
    }));
    const wsHist = XLSX.utils.json_to_sheet(histRows);
    XLSX.utils.book_append_sheet(wb, wsHist, 'Historical Rankings');
  }

  // 4. Exchange Rankings (Rolling)
  if (optimizer.exchange_rankings?.length > 0) {
    const exRows = optimizer.exchange_rankings.map(e => ({
      Exchange: e.exchange,
      'Fee%': e.fee_pct,
      'As Buyer': e.as_buyer,
      'As Seller': e.as_seller,
      'Total Involvement': e.total_involvement,
      'Profit Sum': e.profit_sum,
      'Buy %': e.total_involvement > 0 ? Math.round(e.as_buyer / e.total_involvement * 100) : 0,
      'Sell %': e.total_involvement > 0 ? Math.round(e.as_seller / e.total_involvement * 100) : 0,
    }));
    const wsEx = XLSX.utils.json_to_sheet(exRows);
    XLSX.utils.book_append_sheet(wb, wsEx, 'Exchange (Rolling)');
  }

  // 5. Exchange Rankings (Historical)
  if (optimizer.historical_exchange_rankings?.length > 0) {
    const histExRows = optimizer.historical_exchange_rankings.map(e => {
      const total = e.total_buy_ticks + e.total_sell_ticks;
      return {
        Exchange: e.exchange,
        'Total Buy Ticks': e.total_buy_ticks,
        'Total Sell Ticks': e.total_sell_ticks,
        'Total Profit Sum': e.total_profit_sum,
        'Total Involvement': e.total_involvement,
        'Buy %': total > 0 ? Math.round(e.total_buy_ticks / total * 100) : 0,
        'Sell %': total > 0 ? Math.round(e.total_sell_ticks / total * 100) : 0,
      };
    });
    const wsHistEx = XLSX.utils.json_to_sheet(histExRows);
    XLSX.utils.book_append_sheet(wb, wsHistEx, 'Exchange (Historical)');
  }

  // 6. Exchange Pairs
  if (optimizer.pair_rankings?.length > 0) {
    const pairRows = optimizer.pair_rankings.map((p, i) => ({
      '#': i + 1,
      'Buy Exchange': p.buy_exchange,
      'Sell Exchange': p.sell_exchange,
      'Profitable Ticks': p.trades,
      'Profit Sum': p.profit_sum,
    }));
    const wsPairs = XLSX.utils.json_to_sheet(pairRows);
    XLSX.utils.book_append_sheet(wb, wsPairs, 'Exchange Pairs');
  }

  // 7. Watchlist
  if (optimizer.watchlist?.length > 0) {
    const wlRows = optimizer.watchlist.map(w => ({
      Symbol: w.symbol.replace('USDT', ''),
      'Watching Since': new Date(w.watching_since * 1000).toISOString(),
      'Elapsed (s)': w.elapsed,
      'Progress%': w.progress,
      Confirmed: w.confirmed ? 'YES' : '',
      'Avg Score': w.avg_score,
    }));
    const wsWl = XLSX.utils.json_to_sheet(wlRows);
    XLSX.utils.book_append_sheet(wb, wsWl, 'Watchlist');
  }

  // 8. Rotation History
  if (optimizer.rotations?.length > 0) {
    const rotRows = optimizer.rotations.map(r => ({
      Timestamp: new Date(r.timestamp * 1000).toISOString(),
      'Old Symbol': r.old_symbol.replace('USDT', ''),
      'New Symbol': r.new_symbol.replace('USDT', ''),
      'Old Score': r.old_score,
      'New Score': r.new_score,
      'Switching Cost $': r.switching_cost_usd,
      'Est Improvement $/hr': r.est_hourly_improvement_usd,
    }));
    const wsRot = XLSX.utils.json_to_sheet(rotRows);
    XLSX.utils.book_append_sheet(wb, wsRot, 'Rotation History');
  }

  // 9. Tier Analysis
  if (optimizer.rankings?.length > 0) {
    const tierData = ['T1', 'T2', 'T3', 'T4'].map(t => {
      const syms = optimizer.rankings.filter(r => getTier(r.symbol) === t && r.total_ticks > 0);
      const profCount = syms.filter(s => s.score > 0).length;
      return {
        Tier: t,
        Symbols: syms.length,
        Profitable: profCount,
        '% Profitable': syms.length > 0 ? Math.round(profCount / syms.length * 100) : 0,
        'Avg Score': syms.length > 0 ? syms.reduce((s, r) => s + r.score, 0) / syms.length : 0,
        'Avg Frequency': syms.length > 0 ? syms.reduce((s, r) => s + r.frequency, 0) / syms.length : 0,
        'Total Est $/hr': syms.reduce((s, r) => s + r.est_hourly_profit, 0),
      };
    });
    const wsTier = XLSX.utils.json_to_sheet(tierData);
    XLSX.utils.book_append_sheet(wb, wsTier, 'Tier Analysis');
  }

  // 10. Trade History (ALL trades)
  if (allTrades.length > 0) {
    const hasDemoTrades = allTrades.some(t => t.demo_status);
    const tradeRows = allTrades.map(t => ({
      Timestamp: new Date(t.timestamp * 1000).toISOString(),
      Symbol: t.symbol.replace('USDT', ''),
      'Buy Exchange': t.buy_exchange,
      'Sell Exchange': t.sell_exchange,
      'Buy Price': t.buy_price,
      'Sell Price': t.sell_price,
      'Spread%': t.spread_pct,
      'Fee%': t.fee_pct,
      'Net%': t.net_pct,
      'Profit $': t.profit_usd,
      'Trade Amount $': t.trade_amount,
      'Sim Slippage %': t.sim_slippage_pct ?? '',
      ...(hasDemoTrades ? {
        'Demo Buy $': t.demo_buy_price ?? '',
        'Demo Sell $': t.demo_sell_price ?? '',
        'Demo Profit $': t.demo_profit_usd ?? '',
        'Slippage %': t.demo_slippage_pct ?? '',
        'Latency ms': t.demo_latency_ms ?? '',
        'Demo Status': t.demo_status ?? '',
      } : {}),
    }));
    const wsTrades = XLSX.utils.json_to_sheet(tradeRows);
    XLSX.utils.book_append_sheet(wb, wsTrades, 'Trade History');
  }

  // 11. Transfer History (ALL transfers)
  if (allTransfers.length > 0) {
    const transferRows = allTransfers.map(t => ({
      Timestamp: new Date(t.timestamp * 1000).toISOString(),
      Type: t.type,
      'From Exchange': t.from_exchange,
      'To Exchange': t.to_exchange,
      Symbol: t.symbol,
      'Amount $': t.amount_usd,
      'Fee $': t.fee_usd,
    }));
    const wsTransfers = XLSX.utils.json_to_sheet(transferRows);
    XLSX.utils.book_append_sheet(wb, wsTransfers, 'Transfer History');
  }

  // 12. Transfer Summary (aggregated by type)
  if (allTransfers.length > 0) {
    const typeMap: Record<string, { count: number; totalAmount: number; totalFee: number }> = {};
    for (const t of allTransfers) {
      if (!typeMap[t.type]) typeMap[t.type] = { count: 0, totalAmount: 0, totalFee: 0 };
      typeMap[t.type].count++;
      typeMap[t.type].totalAmount += t.amount_usd;
      typeMap[t.type].totalFee += t.fee_usd;
    }
    const summaryRows = Object.entries(typeMap).map(([type, data]) => ({
      Type: type,
      Count: data.count,
      'Total Amount $': Math.round(data.totalAmount * 100) / 100,
      'Total Fees $': Math.round(data.totalFee * 10000) / 10000,
      'Avg Fee $': data.count > 0 ? Math.round(data.totalFee / data.count * 10000) / 10000 : 0,
    }));
    const wsTransSummary = XLSX.utils.json_to_sheet(summaryRows);
    XLSX.utils.book_append_sheet(wb, wsTransSummary, 'Transfer Summary');
  }

  // 13. Trend Analysis
  if (optimizer.historical_rankings?.length > 0) {
    const trendRows = optimizer.historical_rankings.map(h => {
      let direction = 'STABLE';
      if (h.trend > 0.0001) direction = 'UP';
      else if (h.trend < -0.0001) direction = 'DOWN';
      return {
        Symbol: h.symbol.replace('USDT', ''),
        Tier: getTier(h.symbol),
        'All-Time Score': h.all_time_score,
        'Rolling Score': h.rolling_score,
        Trend: h.trend,
        Direction: direction,
        'Overall Frequency': h.overall_frequency,
        'Est $/hr': h.est_hourly_rate,
        Active: h.is_active ? 'YES' : '',
      };
    });
    trendRows.sort((a, b) => b.Trend - a.Trend);
    const wsTrend = XLSX.utils.json_to_sheet(trendRows);
    XLSX.utils.book_append_sheet(wb, wsTrend, 'Trend Analysis');
  }

  // 14. Buy/Sell Distribution per symbol
  if (optimizer.historical_rankings?.length > 0) {
    // Collect all exchange names
    const allExchanges = new Set<string>();
    for (const h of optimizer.historical_rankings) {
      if (h.buy_exchange_counts) Object.keys(h.buy_exchange_counts).forEach(e => allExchanges.add(e));
      if (h.sell_exchange_counts) Object.keys(h.sell_exchange_counts).forEach(e => allExchanges.add(e));
    }
    const exchanges = [...allExchanges].sort();

    const distRows = optimizer.historical_rankings
      .filter(h => h.total_profitable_ticks > 0)
      .map(h => {
        const row: Record<string, string | number> = {
          Symbol: h.symbol.replace('USDT', ''),
          'Total Profitable Ticks': h.total_profitable_ticks,
        };
        for (const ex of exchanges) {
          row[`Buy@${ex}`] = h.buy_exchange_counts?.[ex] ?? 0;
          row[`Sell@${ex}`] = h.sell_exchange_counts?.[ex] ?? 0;
        }
        return row;
      });
    if (distRows.length > 0) {
      const wsDist = XLSX.utils.json_to_sheet(distRows);
      XLSX.utils.book_append_sheet(wb, wsDist, 'Buy-Sell Distribution');
    }
  }

  // 15. Configurations History
  if (allConfigHistory.length > 0) {
    const configRows = allConfigHistory.map(c => ({
      Timestamp: new Date(c.timestamp * 1000).toISOString(),
      Reason: c.reason,
      'Adaptive Mode': c.adaptive_mode ? 'ON' : 'OFF',
      'Trade Amount $': c.trade_amount,
      'Avg Trade Size $': c.avg_trade_size,
      'Min Net Profit %': c.min_net_profit_pct,
      'Rebalance Cooldown (s)': c.rebalance_cooldown,
      'Miss Streak Threshold': c.min_misses_before_rebalance,
      'ROI Horizon (s)': c.rebalance_roi_horizon,
      'Total Capital $': c.total_capital,
      'Active Symbols': c.num_active_symbols,
      'Max Active': c.max_active_symbols,
      'Est Profit/Trade $': c.estimated_profit_per_trade,
    }));
    const wsConfig = XLSX.utils.json_to_sheet(configRows);
    XLSX.utils.book_append_sheet(wb, wsConfig, 'Configurations');
  }

  // 15b. Fee Configuration Snapshot
  if (feeConfigs && Object.keys(feeConfigs).length > 0) {
    const feeRows = Object.entries(feeConfigs).map(([ex, cfg]) => ({
      Exchange: ex,
      'Base Rate %': (cfg.base_taker_rate * 100).toFixed(4),
      'Token Discount': cfg.token_discount_enabled ? 'ON' : 'OFF',
      'Discount %': (cfg.token_discount_pct * 100).toFixed(1),
      'Effective Rate %': (cfg.effective_taker_rate * 100).toFixed(4),
      'Mechanism': cfg.fee_mechanism,
      'Fee Model': cfg.fee_model,
      'Referral': cfg.referral_enabled ? 'ON' : 'OFF',
      'Referral %': (cfg.referral_cashback_pct * 100).toFixed(1),
      'Settlement (min)': cfg.referral_settlement_minutes,
      'Referrer Commission %': ((cfg.referrer_commission_pct ?? 0) * 100).toFixed(1),
      'After Referral %': (cfg.effective_rate_after_referral * 100).toFixed(4),
      'Zero-Fee Pairs': cfg.zero_fee_pairs.join(', '),
    }));
    const wsFees = XLSX.utils.json_to_sheet(feeRows);
    XLSX.utils.book_append_sheet(wb, wsFees, 'Fee Configuration');
  }

  // 15c. Transfer Configuration Snapshot
  if (transferConfigs && Object.keys(transferConfigs).length > 0) {
    const transferRows: Record<string, unknown>[] = [];
    for (const [ex, cfg] of Object.entries(transferConfigs)) {
      for (const net of cfg.networks) {
        transferRows.push({
          Exchange: ex,
          Network: net.network,
          'Fee $': net.fee,
          Type: net.fee_type,
          '% Rate': net.fee_type === 'percentage' ? (net.percentage_rate * 100).toFixed(1) + '%' : '',
          '% Min $': net.fee_type === 'percentage' ? net.percentage_min : '',
          'Min Withdrawal $': net.min_withdrawal > 0 ? net.min_withdrawal : '',
          'Speed (s)': net.speed_seconds,
          Enabled: net.enabled ? 'YES' : 'NO',
          Notes: net.notes,
        });
      }
      // Summary row
      transferRows.push({
        Exchange: ex,
        Network: `→ Preferred: ${cfg.preferred_network}`,
        'Fee $': `Effective: $${cfg.effective_fee?.toFixed(3) ?? '?'}`,
        Type: '',
        '% Rate': '',
        '% Min $': '',
        'Min Withdrawal $': '',
        'Speed (s)': '',
        Enabled: `Cheapest: ${cfg.cheapest_network ?? '?'}`,
        Notes: '',
      });
    }
    const wsTransfer = XLSX.utils.json_to_sheet(transferRows);
    XLSX.utils.book_append_sheet(wb, wsTransfer, 'Transfer Configuration');
  }

  // 16. Discrepancies (demo vs sim)
  if (demoDiscrepancies.length > 0) {
    const discRows = demoDiscrepancies.map(d => ({
      Timestamp: new Date(d.timestamp * 1000).toISOString(),
      Exchange: d.exchange,
      Type: d.type,
      Symbol: d.symbol.replace('USDT', ''),
      'Sim Value $': Number(d.sim_value.toFixed(4)),
      'Demo Value $': Number(d.demo_value.toFixed(4)),
      'Diff $': Number(d.diff_abs.toFixed(4)),
      'Diff %': Number(d.diff_pct.toFixed(2)),
      'Root Cause': d.root_cause,
    }));
    const wsDisc = XLSX.utils.json_to_sheet(discRows);
    XLSX.utils.book_append_sheet(wb, wsDisc, 'Discrepancies');
  }

  // 17. Hourly P&L (persisted chart data)
  if (hourlyPnl && hourlyPnl.length > 0) {
    const hourlyRows = hourlyPnl.map(h => ({
      Hour: h.hour.replace('_', ' ') + ':00 UTC',
      'Trading P&L $': h.pnl,
      'Transfer Fees $': h.fees,
      'Net P&L $': h.net,
      Trades: h.trades,
    }));
    const wsHourly = XLSX.utils.json_to_sheet(hourlyRows);
    XLSX.utils.book_append_sheet(wb, wsHourly, 'Hourly P&L');
  }

  // 18. Daily P&L (persisted chart data)
  if (dailyPnl && dailyPnl.length > 0) {
    const dailyRows = dailyPnl.map(d => ({
      Date: d.date,
      'Trading P&L $': d.pnl,
      'Transfer Fees $': d.fees,
      'Net P&L $': d.net,
      Trades: d.trades,
    }));
    const wsDaily = XLSX.utils.json_to_sheet(dailyRows);
    XLSX.utils.book_append_sheet(wb, wsDaily, 'Daily P&L');
  }

  // 19. Exchange Profit Contribution (computed from trades)
  if (allTrades.length > 0) {
    const profits = new Map<string, { buy: number; sell: number; total: number; trades: number }>();
    for (const t of allTrades) {
      const half = t.profit_usd / 2;
      const buyEntry = profits.get(t.buy_exchange) ?? { buy: 0, sell: 0, total: 0, trades: 0 };
      buyEntry.buy += half;
      buyEntry.total += half;
      buyEntry.trades++;
      profits.set(t.buy_exchange, buyEntry);

      const sellEntry = profits.get(t.sell_exchange) ?? { buy: 0, sell: 0, total: 0, trades: 0 };
      sellEntry.sell += half;
      sellEntry.total += half;
      sellEntry.trades++;
      profits.set(t.sell_exchange, sellEntry);
    }
    const exProfitRows = [...profits.entries()]
      .sort((a, b) => b[1].total - a[1].total)
      .map(([exchange, data]) => ({
        Exchange: exchange,
        'As Buyer Profit $': Number(data.buy.toFixed(4)),
        'As Seller Profit $': Number(data.sell.toFixed(4)),
        'Total Profit $': Number(data.total.toFixed(4)),
        'Trade Involvements': data.trades,
      }));
    const wsExProfit = XLSX.utils.json_to_sheet(exProfitRows);
    XLSX.utils.book_append_sheet(wb, wsExProfit, 'Exchange Profit');
  }

  // Generate and download
  const ts = now.toISOString().replace(/[:T]/g, '_').slice(0, 15);
  const filename = `coirnabot_rankings_${ts}.xlsx`;
  XLSX.writeFile(wb, filename);
}
