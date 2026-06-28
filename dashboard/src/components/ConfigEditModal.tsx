import { useState, useEffect, useMemo } from 'react';
import { useToast } from './ToastContext';
import FeeManagementTab from './FeeManagementTab';
import Tooltip from './Tooltip';
import type { ExchangeFeeConfig } from '../types';

interface Props {
  configId: string;
  configName: string;
  groupName: string;
  isSuperPrimary: boolean;
  onClose: () => void;
  onSendMessage: (msg: object) => void;
  onSendWithCallback: (msg: object, callback: (data: any) => void) => void;
  /** Globally-fetched 24h volumes (Global tab → App state → here). */
  globalVolumes?: Record<string, Record<string, number>> | null;
}

interface FieldDef {
  key: string;
  label: string;
  /** 'pct' is stored as a fraction (0.04) but displayed as 4 (= 4%). */
  type: 'number' | 'bool' | 'pct';
  min?: number;
  max?: number;
  step?: number;
  fallback: number | boolean;
  hint?: string;
  tooltip?: string;
}

interface SectionDef {
  title: string;
  fields: FieldDef[];
}

const SECTIONS: SectionDef[] = [
  {
    title: 'Trade Sizing',
    fields: [
      { key: 'trade_amount_usd', label: 'Trade Amount ($)', type: 'number', min: 1, fallback: 40, tooltip: "Why it exists: gives the bot a fixed dollar size per trade so slippage stays predictable as capital changes. What changing it does: higher = larger trades, more impact on order book (more slippage), faster capital churn; lower = safer per-trade exposure but more trades needed to deploy capital. Overridden when trade_amount_pct > 0. Default: $40. Config key: trade_amount_usd" },
      { key: 'trade_amount_pct', label: 'Trade Amount % of Capital', type: 'pct', min: 0, max: 100, step: 0.1, fallback: 0.04, tooltip: "Why it exists: auto-scales trade size as the bot's capital grows (or shrinks). Without this, trade_amount_usd stays constant and your effective leverage shrinks as profits compound. What changing it does: higher % = larger trades + more aggressive scaling; lower = more conservative. Recomputed hourly + on discovery transitions. 0 = disabled (use fixed trade_amount_usd instead). Default: 4%. Config key: trade_amount_pct" },
      { key: 'min_net_profit_pct', label: 'Min Net Profit %', type: 'number', min: 0, step: 0.001, fallback: 0.01, tooltip: "Why it exists: filters marginal opportunities — guarantees every executed trade had at least this much net profit after fees + slippage at decision time. What changing it does: lower = more trades, smaller margins per trade (and exposes you to MTM swings during the brief window between decision and execution); higher = fewer trades, but each is more durable. 0 = trade on any positive net. Default: 0.01%. Config key: min_net_profit_pct" },
      { key: 'net_pct_sizing_enabled', label: 'Net%-based Sizing', type: 'bool', fallback: true, tooltip: "Why it exists: fat spreads close fast — if you size every opportunity the same, you under-deploy on the most profitable ticks and waste capital on thin ones. What changing it does: ON = trade size scales with the current tick's net% (>0.25% gets up to 2.5×, <0.03% gets 0.5×); OFF = every trade uses the base size regardless of margin. Default: ON. Config key: net_pct_sizing_enabled" },
      { key: 'net_pct_multiplier_cap', label: 'Net% Multiplier Cap', type: 'number', min: 1, step: 0.1, fallback: 2.5, tooltip: "Why it exists: caps how aggressively net%-based sizing upsizes on fat spreads — prevents a single huge tick from concentrating most of your capital into one trade with high slippage. What changing it does: higher = bigger size on rare fat spreads (more profit, more order-book impact); lower = more conservative. Default: 2.5×. Config key: net_pct_multiplier_cap" },
      { key: 'adaptive_mode', label: 'Adaptive Mode', type: 'bool', fallback: true, tooltip: "Why it exists: not all active symbols deserve the same trade size — strong-tier symbols (high score) earn more aggressive sizing, weak-tier active symbols get a 1.0× floor so capital still trades. What changing it does: ON = per-symbol focus-tier multipliers (strong 2-3×, very_strong 3-4×, normal 0.5-1.5×); OFF = every active symbol trades at base size. Recommended ON. Default: ON. Config key: adaptive_mode" },
    ],
  },
  {
    title: 'Discovery & Scoring',
    fields: [
      { key: 'discovery_duration', label: 'Discovery Duration (s)', type: 'number', min: 60, fallback: 300, tooltip: "Why it exists: gives the bot enough data to rank 60+ symbols before committing capital. Without discovery the bot would activate on a single noisy tick. What changing it does: longer = more accurate ranking but slower first-trade; shorter = faster start but riskier picks. Auto-extends up to 3600s if no candidates qualify. Default: 300s. Config key: discovery_duration" },
      { key: 'scoring_window', label: 'Scoring Window (s)', type: 'number', min: 60, fallback: 1800, tooltip: "Why it exists: defines how much rolling tick history feeds into each symbol's score (avg_profitable_net × frequency). Longer window = more signal but slower reaction to regime changes. What changing it does: longer = stickier rankings, fewer rotations; shorter = chases recent winners + more thrashing. CHANGING TRIGGERS DISCOVERY RESTART (wipes tick window). Default: 1800s (30 min). Config key: scoring_window" },
      { key: 'evaluation_interval', label: 'Eval Interval (s)', type: 'number', min: 30, fallback: 120, tooltip: "Why it exists: rotation/expansion/demotion checks are expensive and shouldn't run every tick. This caps how often they fire. What changing it does: lower = faster reaction to score changes (more rotation churn + fee bleed); higher = stickier active set. Default: 120s. Config key: evaluation_interval" },
      { key: 'auto_rotate', label: 'Auto-Rotate Symbols', type: 'bool', fallback: true, tooltip: "Why it exists: the best symbols change throughout a session — auto-rotation drops weak performers and promotes new winners. What changing it does: ON = active set drifts toward current best symbols; OFF = locks in whatever discovery picked, no rotation. CHANGING TRIGGERS DISCOVERY RESTART. Default: ON. Config key: auto_rotate" },
      { key: 'num_active_symbols', label: 'Active Symbols (target)', type: 'number', min: 1, fallback: 4, tooltip: "Why it exists: spreads risk across multiple symbols so a single bad symbol doesn't dominate P&L. Below this count, the bot auto-expands aggressively. What changing it does: higher = more diversification but capital spread thinner per symbol (each gets less of trade_amount × multiplier); lower = concentrated bets. CHANGING TRIGGERS DISCOVERY RESTART. Default: 4. Config key: num_active_symbols" },
      { key: 'max_active_symbols', label: 'Max Active Symbols', type: 'number', min: 1, fallback: 6, tooltip: "Why it exists: caps dynamic expansion — even when many symbols look profitable, beyond this many the per-symbol slice gets too thin to overcome fees. What changing it does: higher = more parallelism (but smaller slices and more rebalancing); lower = stays focused on top picks. Default: 6. Config key: max_active_symbols" },
      { key: 'safety_multiplier', label: 'Rotation Safety Multiplier', type: 'number', min: 1, step: 0.1, fallback: 2.0, tooltip: "Why it exists: prevents thrashing the active set on minor score fluctuations. A new candidate must beat the worst current symbol's score by this multiple to trigger rotation. What changing it does: higher = stickier active set (rare rotations, low churn fees); lower = chases the current best more aggressively (more fees from rotation). Default: 2.0×. Config key: safety_multiplier" },
      { key: 'fast_track_discovery_enabled', label: 'Fast-Track Discovery', type: 'bool', fallback: true, tooltip: "Why it exists: when a candidate is clearly good (rising trajectory, strong score), waiting the full discovery window is pure delay. Fast-track exits early. What changing it does: ON = strong+rising candidates exit in ~30s × aggressiveness, normal+rising in 240s, declining waits full window; OFF = every config waits the full discovery_duration. Default: ON. Config key: fast_track_discovery_enabled" },
      { key: 'fast_track_aggressiveness', label: 'Fast-Track Aggressiveness', type: 'number', min: 0.1, max: 3.0, step: 0.1, fallback: 1.0, tooltip: "Why it exists: lets you tune fast-track without flipping the toggle. The base wait times (30s strong+rising, 60s strong+stable, 240s normal+rising, 300s normal+stable) are multiplied by this. What changing it does: <1 = exit faster (more risk of activating noise); >1 = wait longer (safer, slower first trade). Default: 1.0×. Config key: fast_track_aggressiveness" },
    ],
  },
  {
    title: 'Score Thresholds',
    fields: [
      { key: 'trading_score_threshold', label: 'Trading Score Threshold', type: 'number', min: 0, step: 0.001, fallback: 0.003, tooltip: "Why it exists: filters out symbols with weak edge so capital concentrates on profitable ones. Score = avg_profitable_net% × frequency, so 0.003 means roughly avg_net 0.05% × 6% freq. What changing it does: higher = only strong opportunities activate (fewer trades, better quality); lower = more permissive (more activations including marginal ones). Default: 0.003. Config key: trading_score_threshold" },
      { key: 'strong_score_threshold', label: 'Strong Score Threshold', type: 'number', min: 0, step: 0.01, fallback: 0.1, tooltip: "Why it exists: defines the 'strong' focus tier — these symbols get 2-3× trade multiplier and faster watchlist confirmation (confirmation_period × 0.4). What changing it does: higher = harder to qualify for strong sizing (more conservative); lower = more symbols get aggressive sizing. Default: 0.1. Config key: strong_score_threshold" },
      { key: 'very_strong_score_threshold', label: 'Very Strong Score Threshold', type: 'number', min: 0, step: 0.01, fallback: 0.3, tooltip: "Why it exists: defines the 'very strong' focus tier — these get 3-4× trade multiplier, up to 3 dominant exchanges per direction, and fastest activation (confirmation × 0.1). What changing it does: higher = reserved for truly exceptional opportunities; lower = upgrades more symbols to top sizing. Default: 0.3. Config key: very_strong_score_threshold" },
      { key: 'fee_threshold_multiplier', label: 'Fee Threshold Multiplier', type: 'number', min: 0, step: 0.1, fallback: 0.2, tooltip: "Why it exists: cheap pairs (Bitfinex+MEXC ~0.04% fees) deserve a lower activation bar than expensive pairs (Binance+OKX ~0.18%). Otherwise expensive routes activate on tight spreads where they can't actually profit. What changing it does: higher = much stricter on expensive pairs; lower = treats all pairs alike. 0 = no fee adjustment. Default: 0.2. Config key: fee_threshold_multiplier" },
      { key: 'promotion_threshold', label: 'Promotion Threshold', type: 'number', min: 0, step: 0.0001, fallback: 0.0001, tooltip: "Why it exists: gates how much score improvement is needed to promote a candidate INTO the active set during rotation evaluation. What changing it does: higher = candidates must clearly beat existing slots; lower = easier to break in. Default: 0.0001. Config key: promotion_threshold" },
      { key: 'demotion_threshold', label: 'Demotion Threshold', type: 'number', min: 0, step: 0.0001, fallback: 0, tooltip: "Why it exists: secondary demotion gate beyond the strong-tier check. Useful if you want to keep symbols active even after their score drops below strong, until they hit some absolute floor. What changing it does: 0 = use strong-tier check only (default behavior); >0 = additional floor below which symbols are demoted regardless of tier. Default: 0. Config key: demotion_threshold" },
      { key: 'demotion_period', label: 'Demotion Period (s)', type: 'number', min: 30, fallback: 1800, tooltip: "Why it exists: prevents demoting a symbol on a brief score dip. The symbol must stay below threshold for this duration before it's actually demoted. What changing it does: longer = stickier active set (waits to confirm decline); shorter = drops weak symbols faster. Default: 1800s (30 min). Config key: demotion_period" },
      { key: 'demotion_cooldown_multiplier', label: 'Demotion Cooldown Mult', type: 'number', min: 1, step: 0.5, fallback: 7.0, tooltip: "Why it exists: after a symbol is demoted, this prevents it from immediately re-activating and thrashing in/out. Cooldown = demotion_period × this. What changing it does: higher = longer ban on a recently-bad symbol; lower = re-activates faster (risk of churn). Default: 7×. Config key: demotion_cooldown_multiplier" },
      { key: 'confirmation_period', label: 'Confirmation Period (s)', type: 'number', min: 30, fallback: 120, tooltip: "Why it exists: a candidate must demonstrate stability over this window before activation, preventing single-tick spikes from triggering trades. What changing it does: longer = safer (filters more noise) but slower first trade; shorter = faster activation but more false starts. Strong tier uses × 0.4, very_strong × 0.1. Default: 120s. Config key: confirmation_period" },
      { key: 'score_stability_seconds', label: 'Score Stability (s)', type: 'number', min: 10, fallback: 180, tooltip: "Why it exists: minimum observation time before any candidate (regardless of score) can activate. Prevents activating on the first 1-second spike when a fresh symbol enters. What changing it does: longer = more conservative (waits for sustained signal); shorter = activates faster on initial promising data. Default: 180s. Config key: score_stability_seconds" },
      { key: 'score_stability_factor', label: 'Score Stability Factor', type: 'number', min: 0, max: 1, step: 0.05, fallback: 0.5, tooltip: "Why it exists: cliff-drop detection — rejects candidates whose score has crashed from a recent peak. If current_score < peak × this, the candidate is rejected as 'declining'. What changing it does: lower = stricter (only accept candidates near their peak); higher = more permissive (accepts even after big drops). Default: 0.5 (50% drop tolerated). Config key: score_stability_factor" },
    ],
  },
  {
    title: 'Rebalance Gates',
    fields: [
      { key: 'rebalance_cooldown', label: 'Rebalance Cooldown (s)', type: 'number', min: 1, fallback: 10, tooltip: "Why it exists: prevents the rebalancer from firing on every tick — without a cooldown, transient depletions get fixed instantly and refire seconds later, wasting taker fees on internal sells. What changing it does: longer = fewer rebalances + less fee burn but more SIZE_ZERO skips waiting for capital to arrive; shorter = faster recovery from imbalance + more fees. Default: 10s. Config key: rebalance_cooldown" },
      { key: 'min_misses_before_rebalance', label: 'Min Misses Before Rebalance', type: 'number', min: 1, fallback: 3, tooltip: "Why it exists: a single missed trade isn't worth firing a rebalance for. The bot waits for N consecutive misses before deciding the pair has a real capital problem. What changing it does: higher = more patient (fewer rebalances, bigger backlogs); lower = aggressive (catches problems fast, more fees). Cheap-transfer pairs auto-divide by 3 (min 3); semi-cheap by 2 (min 5). Default: 3. Config key: min_misses_before_rebalance" },
      { key: 'rebalance_roi_horizon', label: 'Rebalance ROI Horizon (s)', type: 'number', min: 60, fallback: 1800, tooltip: "Why it exists: a rebalance only makes sense if its fee will be recovered by future trades. This sets the time horizon over which the bot amortizes the fee cost vs expected profit. What changing it does: longer = more rebalances pass the gate (bot bets on long-term recovery); shorter = stricter, only worth-it rebalances fire. Default: 1800s (30 min). Config key: rebalance_roi_horizon" },
      { key: 'rebalance_roi_divisor', label: 'Rebalance ROI Divisor', type: 'number', min: 1, fallback: 5, tooltip: "Why it exists: ROI threshold for a rebalance = fee_rate / divisor. Higher divisor = lower threshold = easier to pass. What changing it does: higher (5-10) = small capital can rebalance more freely; lower (2-3) = strict ROI gate, suits larger capital where fees are smaller relative to trade size. Default: 5. Config key: rebalance_roi_divisor" },
      { key: 'reallocation_cost_horizon', label: 'Reallocation Cost Horizon (h)', type: 'number', min: 0.5, step: 0.5, fallback: 4.0, tooltip: "Why it exists: when dominant exchanges shift, moving capital to the new pair costs taker fees on both sides. This sets the hours of expected profit needed to justify the cost. What changing it does: higher = stickier pairs (rotates rarely, low churn fees); lower = chases tick-level winners aggressively (high fee bleed observed in S31). Default: 4h. Config key: reallocation_cost_horizon" },
      { key: 'min_rebalance_score', label: 'Min Rebalance Score', type: 'number', min: 0, step: 0.0001, fallback: 0.0001, tooltip: "Why it exists: low-scoring symbols don't deserve rebalancing — paying transfer fees to top up a barely-profitable symbol bleeds capital. What changing it does: higher = only proven winners get fee-paying rebalances; lower = more permissive. Default: 0.0001. Config key: min_rebalance_score" },
      { key: 'hourly_external_transfer_cap', label: 'Hourly Transfer Cap ($)', type: 'number', min: 0, step: 0.5, fallback: 5.0, tooltip: "Why it exists: caps total external withdrawal fees per rolling hour to prevent runaway transfer costs during volatile periods. Without this, a chain of 5 expensive transfers ($1+ each) can wipe out an hour of arb profit. What changing it does: higher = more transfer flexibility; lower = forces the bot to use cheaper internal routes. 0 = unlimited (disable). Zero/near-zero fee transfers (≤$0.01) bypass this cap. Default: $5/hr. Config key: hourly_external_transfer_cap" },
      { key: 'net_pnl_gate_warmup_trades', label: 'Net P&L Gate Warmup Trades', type: 'number', min: 0, fallback: 10, tooltip: "Why it exists: the net-P&L gate (which blocks rebalances when trading_pnl + cashback < transfer_fees) shouldn't fire before the bot has had time to prove itself. This is the trade count after which the gate activates. What changing it does: higher = more lenient early period (gate fires later); lower = strict from the start. Default: 10 trades. Config key: net_pnl_gate_warmup_trades" },
      { key: 'net_pnl_gate_grace_seconds', label: 'Net P&L Gate Grace (s)', type: 'number', min: 0, fallback: 1800, tooltip: "Why it exists: even after the trade-count warmup, the bot needs time to recover from initial setup fees before the rotation gate slams shut on a negative net P&L. What changing it does: longer = more time to climb out of early-session red; shorter = quickly locks down rotation when bleeding. Default: 1800s (30 min). Config key: net_pnl_gate_grace_seconds" },
    ],
  },
  {
    title: 'Capital Architecture',
    fields: [
      { key: 'trading_float_multiplier', label: 'Trading Float Multiplier', type: 'number', min: 0, step: 0.5, fallback: 6.7, tooltip: "Why it exists: Bitfinex has 0% taker fees and 0% withdrawals — keeping a working USDT float there enables the cheapest buy leg. The float target is sized by trade_amount (not capital), so exposure stays bounded as you grow. What changing it does: higher = bigger Bitfinex float (more capital sitting on a single venue, but fewer replenish round-trips); lower = less Bitfinex exposure but more cross-exchange transfers. 0 = trading float DISABLED entirely (no Bitfinex carve-out, no replenish, no overflow). Default: 6.7×. Config key: trading_float_multiplier" },
      { key: 'trading_float_replenish_trigger', label: 'Replenish Trigger', type: 'number', min: 0, step: 0.5, fallback: 3.0, tooltip: "Why it exists: when the Bitfinex float drains during trading, the bot pulls fresh USDT from the custody hub (via Aptos $0). This sets the threshold — replenish fires when bitfinex_usdt < trade_amount × this. What changing it does: higher = top up sooner (less risk of running dry mid-trade); lower = let the float drain further (fewer replenish transfers). 0 = never auto-replenish (manual top-ups only). Default: 3.0×. Config key: trading_float_replenish_trigger" },
      { key: 'trading_float_overflow_multiplier', label: 'Overflow Multiplier', type: 'number', min: 0, step: 0.1, fallback: 1.5, tooltip: "Why it exists: when sells accumulate USDT on Bitfinex above the target, the excess should flow back to the custody hub for safer parking — Bitfinex isn't third-party PoR audited. Sweep fires when bitfinex_usdt > target × this. What changing it does: higher = lets more capital pile up on Bitfinex before sweeping (fewer overflow transfers); lower = keeps Bitfinex tightly at target (more sweeps). 0 = never sweep overflow. Default: 1.5×. Config key: trading_float_overflow_multiplier" },
    ],
  },
  {
    title: 'Inventory & Momentum',
    fields: [
      { key: 'momentum_filter_enabled', label: 'Momentum Filter', type: 'bool', fallback: true, tooltip: "Why it exists: arbitrage holds inventory, so a falling price hurts even if every individual trade is profitable. The momentum filter penalizes symbols whose price has trended down so the bot stops accumulating bleeders. What changing it does: ON = scoring multiplied by 1+price_change (capped); OFF = scores ignore price direction (more trades on falling symbols). Default: ON. Config key: momentum_filter_enabled" },
      { key: 'momentum_lookback_hours', label: 'Momentum Lookback (h)', type: 'number', min: 1, fallback: 24, tooltip: "Why it exists: defines how far back the momentum filter measures price drift. Too short = catches noise; too long = slow to react to fresh trends. What changing it does: longer = smoother momentum signal (rejects only sustained declines); shorter = more reactive. Default: 24h. Config key: momentum_lookback_hours" },
      { key: 'momentum_sample_interval_minutes', label: 'Momentum Sample Interval (min)', type: 'number', min: 1, fallback: 60, tooltip: "Why it exists: samples the symbol's mid-price every N minutes to compute the momentum factor. More samples = smoother but more memory. What changing it does: shorter = finer resolution (catches sharp moves); longer = coarser (filters intra-hour noise). Default: 60min. Config key: momentum_sample_interval_minutes" },
      { key: 'momentum_min_factor', label: 'Momentum Min Factor', type: 'number', min: 0, max: 1, step: 0.05, fallback: 0.3, tooltip: "Why it exists: clamps how much the momentum filter can penalize a falling symbol. Without a floor, an 80% crash would zero out the score completely; with a floor, the symbol keeps a tiny chance of activation. What changing it does: lower = harsher penalty for declining symbols; higher = milder. Default: 0.3 (max 70% score reduction). Config key: momentum_min_factor" },
      { key: 'momentum_max_factor', label: 'Momentum Max Factor', type: 'number', min: 1, step: 0.1, fallback: 1.5, tooltip: "Why it exists: clamps how much the momentum filter can BOOST a rising symbol's score. Prevents a parabolic bull run from over-concentrating capital on one momentum-driven symbol. What changing it does: higher = lets rising symbols dominate; lower = keeps momentum boost modest. Default: 1.5 (max 50% score boost). Config key: momentum_max_factor" },
      { key: 'inventory_rebalance_enabled', label: 'Inventory Rebalance', type: 'bool', fallback: true, tooltip: "Why it exists: trading naturally drifts the 50/50 USDT/crypto target on each exchange — buyers accumulate crypto, sellers accumulate USDT. This periodically resets the drift to lock in value before further price moves. What changing it does: ON = inventory normalized every interval (small taker fee per correction); OFF = drift compounds until natural reverse trades correct it. Default: ON. Config key: inventory_rebalance_enabled" },
      { key: 'inventory_rebalance_interval_hours', label: 'Inventory Rebalance Interval (h)', type: 'number', min: 1, fallback: 6, tooltip: "Why it exists: how often the inventory drift correction fires. Too frequent = excessive taker fees; too rare = drift compounds and locks in MTM losses. What changing it does: shorter = tighter rebalancing (more fees but lower exposure); longer = more drift tolerated (fewer fees but more MTM risk). Default: 6h. Config key: inventory_rebalance_interval_hours" },
      { key: 'inventory_drift_threshold', label: 'Drift Threshold', type: 'number', min: 0, max: 1, step: 0.05, fallback: 0.3, tooltip: "Why it exists: only correct drift that's actually meaningful. A 5% imbalance isn't worth a taker fee. What changing it does: lower = corrects small imbalances (more fees, tighter target); higher = lets drift run further before correction. Default: 0.30 (30% deviation triggers correction). Config key: inventory_drift_threshold" },
    ],
  },
  {
    title: 'Diversification & Auto-Expand',
    fields: [
      { key: 'auto_expand_on_understaff', label: 'Auto-Expand on Understaff', type: 'bool', fallback: true, tooltip: "Why it exists: when symbols get demoted, the active set drops below min — without intervention you'd wait up to a full eval_interval before adding replacements, leaving capital idle. This bypasses the cooldown specifically when understaffed. What changing it does: ON = expansion fires within ~1 min of going below min; OFF = waits the normal eval_interval. Default: ON. Config key: auto_expand_on_understaff" },
      { key: 'diversification_floor_enabled', label: 'Diversification Floor', type: 'bool', fallback: true, tooltip: "Why it exists: when the active set is below min, you'd rather activate a marginal symbol than sit empty. This relaxes the activation threshold proportionally. What changing it does: ON = activation easier when understaffed (fills slots faster, may activate weaker symbols); OFF = strict threshold regardless of staffing. Default: ON. Config key: diversification_floor_enabled" },
      { key: 'diversification_floor_multiplier', label: 'Diversification Floor Multiplier', type: 'number', min: 0, max: 1, step: 0.05, fallback: 0.5, tooltip: "Why it exists: how much the activation threshold gets relaxed when understaffed. Lower = more aggressive filling. What changing it does: 0.5 = threshold halved when below min; 0.7 = threshold × 0.7 (less aggressive); 1.0 = no relaxation. Default: 0.5. Config key: diversification_floor_multiplier" },
      { key: 'auto_disable_volume_enabled', label: 'Auto-Disable Low Volume', type: 'bool', fallback: true, tooltip: "Why it exists: low-volume (exchange, symbol) pairs hit slippage hard and can't fill at quoted prices. The daily auto-disable scans 24h volumes and blocks these pairs preemptively. What changing it does: ON = pairs below threshold auto-blocked at 00:01 UTC daily; OFF = no auto-blocking (manual blocklist still respected). Default: ON. Config key: auto_disable_volume_enabled" },
      { key: 'auto_disable_volume_threshold_usd', label: 'Auto-Disable Threshold ($)', type: 'number', min: 0, step: 1000, fallback: 10000, tooltip: "Why it exists: the volume floor below which a (exchange, symbol) pair gets auto-blocked. Rule of thumb: ~250× max trade size — anything thinner risks slippage > the arb edge. What changing it does: higher = blocks more pairs (safer, fewer trade opportunities); lower = allows thinner books (more slippage risk). 0 = never auto-disable. Default: $10,000/24h. Config key: auto_disable_volume_threshold_usd" },
    ],
  },
  {
    title: 'Simulation Realism',
    fields: [
      { key: 'spread_persistence_ticks', label: 'Spread Persistence Ticks', type: 'number', min: 0, max: 5, fallback: 1, tooltip: "Why it exists: a profitable spread that exists for 1 tick (~1s) often closes before real orders arrive. Persistence requires the spread to survive across N consecutive ticks before trading. What changing it does: higher = filters more phantom spreads (fewer trades but each is more durable); lower = trades on first sight (more trades but more execution risk). 0 = disabled (instant execution, legacy behavior). Default: 1. Config key: spread_persistence_ticks" },
      { key: 'event_driven_seller_penalty_pct', label: 'Event-Driven Seller Penalty %', type: 'number', min: 0, max: 1, step: 0.01, fallback: 0.02, tooltip: "Why it exists: event-driven exchanges (Bitfinex) update bids every 10-20s vs ~100ms for streaming exchanges (Binance, Bybit). The displayed bid is often stale — the actual fill price is worse. This deduction approximates that staleness. What changing it does: higher = stronger preference for streaming exchanges as sellers; lower = treats all sellers equally. 0 = no penalty (use only when you trust event-driven feeds). Default: 0.02%. Config key: event_driven_seller_penalty_pct" },
      { key: 'one_leg_failure_rate', label: 'One-Leg Failure Rate', type: 'number', min: 0, max: 1, step: 0.01, fallback: 0.02, tooltip: "Why it exists: in real trading, occasionally one leg of an arbitrage fills while the other fails — leaving you with a directional position to unwind at a loss. This simulates that risk so simulated P&L approximates live P&L. What changing it does: higher = harsher simulation (matches volatile / poorly-connected exchanges); lower = optimistic simulation. 0 = no one-leg simulation. Default: 0.02 (2%). Config key: one_leg_failure_rate" },
      { key: 'one_leg_unwind_slippage_mult', label: 'One-Leg Unwind Slippage Mult', type: 'number', min: 1, step: 0.1, fallback: 1.5, tooltip: "Why it exists: when a one-leg failure happens, unwinding the orphaned leg costs taker fee + slippage. Slippage on the unwind is typically worse than on the original trade (you're moving against the book). What changing it does: higher = more pessimistic unwind cost (more conservative simulation); lower = optimistic. Default: 1.5×. Config key: one_leg_unwind_slippage_mult" },
      { key: 'max_position_multiplier', label: 'Max Position Multiplier', type: 'number', min: 0, max: 50, step: 0.5, fallback: 3.0, tooltip: "Why it exists: caps how much crypto can accumulate on a single buyer-exchange/symbol — without this cap, a one-sided market could pile up exposure that takes hours to unwind, leaving the bot vulnerable to flash crashes. What changing it does: higher = more capital can sit on one buyer (catches more opportunities but more flash-crash risk); lower = forces faster turnover. 0 = no cap (unlimited accumulation). Default: 3.0× (cap = trade_amount × 3). Config key: max_position_multiplier" },
    ],
  },
  {
    title: 'Anomaly Protection',
    fields: [
      { key: 'anomaly_protection_enabled', label: 'Anomaly Protection', type: 'bool', fallback: true, tooltip: "Why it exists: master kill switch for the 3-layer anomaly system. Layer 1 = circuit breaker (rolling P&L), Layer 2 = drawdown (peak-to-trough), Layer 3 = per-symbol loss streak. Without this, runaway losses go unchecked. What changing it does: ON = full safety stack active; OFF = no automatic pause/block (use this only for testing). Default: ON. Config key: anomaly_protection_enabled" },
      { key: 'circuit_breaker_window', label: 'Circuit Breaker Window (s)', type: 'number', min: 60, fallback: 900, tooltip: "Why it exists: rolling P&L is computed over this window — too short reacts to noise, too long misses fast deteriorations. What changing it does: longer = smoother gauge (slower pause, more loss before triggering); shorter = jumpy (catches fast bleeds but more false alarms). Default: 900s (15 min). Config key: circuit_breaker_window" },
      { key: 'circuit_breaker_threshold', label: 'Circuit Breaker Threshold ($)', type: 'number', max: 0, fallback: -5.0, tooltip: "Why it exists: when rolling P&L over the window drops below this dollar amount, all trading halts. The dollar (not %) form keeps the gate scaled to your capital. What changing it does: more negative (e.g., -$10) = tolerates bigger losses before pausing; less negative (e.g., -$2) = halts on small losses. Default: -$5.00. Config key: circuit_breaker_threshold" },
      { key: 'circuit_breaker_resume_pct', label: 'Resume %', type: 'number', min: 0.1, max: 1, step: 0.1, fallback: 0.5, tooltip: "Why it exists: after a circuit-breaker pause, the bot waits to resume until P&L recovers. This is the recovery fraction — auto-resume when rolling_pnl > threshold × this. What changing it does: lower (0.1) = quick resume on partial recovery; higher (0.9) = waits for full recovery. Default: 0.5 (resume at 50% recovery). Config key: circuit_breaker_resume_pct" },
      { key: 'circuit_breaker_cooldown', label: 'Circuit Breaker Cooldown (s)', type: 'number', min: 30, fallback: 300, tooltip: "Why it exists: minimum wait before auto-resume can fire, regardless of P&L recovery. Prevents instant re-pause cycles when conditions are still volatile. What changing it does: longer = more time for conditions to stabilize; shorter = re-engages faster. Default: 300s. Config key: circuit_breaker_cooldown" },
      { key: 'drawdown_threshold_pct', label: 'Drawdown Threshold %', type: 'number', min: 0.5, max: 20, step: 0.5, fallback: 15.0, tooltip: "Why it exists: per-symbol block threshold based on portfolio peak-to-trough. When breached, only symbols with crypto exposure get blocked — other symbols keep trading. Soft throttle, not a full halt. What changing it does: lower = blocks symbols on smaller drawdowns (more conservative); higher = tolerates more decline before blocking. Default: 15%. Config key: drawdown_threshold_pct" },
      { key: 'drawdown_resume_pct', label: 'Drawdown Resume %', type: 'number', min: 0.1, max: 10, step: 0.5, fallback: 3.0, tooltip: "Why it exists: after blocking symbols on drawdown, the bot needs a recovery threshold before unblocking them. What changing it does: lower = unblocks faster (resumes trading earlier in recovery); higher = waits longer to confirm recovery is real. Default: 3%. Config key: drawdown_resume_pct" },
      { key: 'drawdown_emergency_mult', label: 'Drawdown Emergency Mult (legacy)', type: 'number', min: 1.5, max: 5, step: 0.1, fallback: 2.0, tooltip: "LEGACY — kept for back-compat. The new two-layer emergency gate (Layer A + Layer B below) replaces this. Old v0.30 behavior: emergency sell-all when MTM drawdown ≥ drawdown_threshold × this. Default: 2.0× (= 30% MTM emergency). Config key: drawdown_emergency_mult" },
      { key: 'realized_drawdown_emergency_pct', label: 'Layer A: Realized DD Emergency %', type: 'number', min: 1, max: 50, step: 0.5, fallback: 15.0, tooltip: "Why it exists: PRIMARY emergency gate. Fires on realized-capital drawdown — capital that's actually been locked in (initial + closed P&L − fees + cashback). Realized capital can't move on MTM noise, so phantom drops (in-transit funds, hedge basis change, flash quotes) never trigger this. What changing it does: lower = halts on smaller real losses; higher = tolerates more before halting. Default: 15%. Config key: realized_drawdown_emergency_pct" },
      { key: 'combined_drawdown_emergency_pct', label: 'Layer B: Combined DD Emergency %', type: 'number', min: 1, max: 80, step: 0.5, fallback: 25.0, tooltip: "Why it exists: hedge-health gate. Fires when combined spot+hedge unrealized drawdown crosses this % AND persists past the sustained-seconds window. If the hedge offsets spot moves correctly, combined drawdown stays near 0 and this never fires. Catches scenarios where the hedge is broken/missing/under-sized. What changing it does: lower = halts on smaller combined moves (catches hedge failures earlier); higher = waits for big breaks. Default: 25%. Config key: combined_drawdown_emergency_pct" },
      { key: 'combined_drawdown_sustained_seconds', label: 'Layer B: Sustained Breach (s)', type: 'number', min: 30, max: 3600, step: 30, fallback: 300, tooltip: "Why it exists: filters transient phantom drawdowns (in-transit funds, flash quotes, hedge basis change). Layer B only fires if the breach persists for this long — real hedge failures persist; phantoms revert in seconds. What changing it does: shorter = catches problems faster but risks tripping on transients; longer = lets problems run longer before halting. Default: 300s (5 min). Config key: combined_drawdown_sustained_seconds" },
      { key: 'emergency_auto_liquidate', label: 'Auto-Liquidate on Emergency', type: 'bool', fallback: false, tooltip: "Why it exists: when emergency fires, do you want auto-sell-all (legacy panic mode) or just halt + alert (let the operator decide)? Auto-sell crystallizes any paper loss as real loss — usually the wrong move. What changing it does: OFF = halt trading + send email + wait for operator; ON = sell-all crypto positions immediately (v0.30 legacy behavior). Default: OFF. Config key: emergency_auto_liquidate" },
      { key: 'symbol_loss_streak_threshold', label: 'Symbol Loss Streak Threshold', type: 'number', min: 2, max: 20, fallback: 4, tooltip: "Why it exists: a symbol that's lost N consecutive trades is misbehaving — block it before it bleeds more. Other symbols keep trading. Targeted protection, not a global halt. What changing it does: lower = blocks misbehaving symbols faster (tighter, may over-react to short streaks); higher = tolerates more losses before sidelining. Default: 4. Config key: symbol_loss_streak_threshold" },
      { key: 'symbol_loss_streak_cooldown', label: 'Symbol Loss Streak Cooldown (s)', type: 'number', min: 60, fallback: 300, tooltip: "Why it exists: how long a streak-blocked symbol stays sidelined before being eligible again. Streak resets after cooldown. What changing it does: longer = bigger penalty box (avoids same symbol re-bleeding); shorter = quicker rehabilitation. Default: 300s. Config key: symbol_loss_streak_cooldown" },
      { key: 'warning_pnl_pct', label: 'Warning P&L %', type: 'number', min: 0.1, max: 1, step: 0.1, fallback: 0.5, tooltip: "Why it exists: a soft-warning level BEFORE the circuit breaker fires — when rolling P&L approaches threshold × this fraction, trade size is halved as a safety brake. What changing it does: lower (0.3) = warning fires earlier in the descent; higher (0.8) = warning fires close to the actual pause. Default: 0.5 (warning at 50% of the way to threshold). Config key: warning_pnl_pct" },
    ],
  },
  {
    title: 'Funding & Hedging',
    fields: [
      { key: 'funding_aware_scoring_enabled', label: 'Funding-Aware Scoring', type: 'bool', fallback: true, tooltip: "Why it exists: holding a hedged spot+short position earns/pays funding every period. Symbols with negative funding (you pay to be short) erode arb profit; positive funding adds to it. This bakes funding into the scoring so symbol selection prefers profitable funding regimes. What changing it does: ON = scores multiplied by 1+annualized_short% (positive funding boosts, negative penalizes); OFF = funding ignored. Default: ON. Config key: funding_aware_scoring_enabled" },
      { key: 'funding_skip_threshold_4h_pct', label: 'Funding Skip 4h %', type: 'number', step: 0.01, fallback: -0.05, tooltip: "Why it exists: for symbols with 4h funding cycles, when the per-period funding is worse than this, the symbol's score gets floored at min_factor (effectively disqualifying it). Catches the worst funding regimes. What changing it does: more negative (-0.10) = tolerates more bad funding before skipping; less negative (-0.02) = skips on milder negative funding. Default: -0.05% per 4h. Config key: funding_skip_threshold_4h_pct" },
      { key: 'funding_skip_threshold_8h_pct', label: 'Funding Skip 8h %', type: 'number', step: 0.01, fallback: -0.05, tooltip: "Why it exists: same as the 4h threshold but for symbols on 8h funding cycles (most majors). What changing it does: same trade-off as the 4h variant — more negative = lenient, less negative = strict. Default: -0.05% per 8h. Config key: funding_skip_threshold_8h_pct" },
      { key: 'funding_score_min_factor', label: 'Funding Min Factor', type: 'number', min: 0.05, max: 1, step: 0.05, fallback: 0.3, tooltip: "Why it exists: lower clamp on the funding score multiplier — prevents extreme negative funding from making the score zero (the symbol is still POTENTIALLY tradeable, just heavily penalized). What changing it does: lower (0.1) = harsher penalty for bad funding (almost zeros score); higher (0.5) = milder penalty. Default: 0.3 (max 70% score reduction). Config key: funding_score_min_factor" },
      { key: 'funding_score_max_factor', label: 'Funding Max Factor', type: 'number', min: 1, step: 0.1, fallback: 1.5, tooltip: "Why it exists: upper clamp on the funding multiplier — prevents extreme positive funding from over-rating a symbol that might have other issues. What changing it does: higher (2.0) = lets positive funding boost the score more aggressively; lower (1.2) = caps the boost. Default: 1.5 (max 50% score boost). Config key: funding_score_max_factor" },
      { key: 'funding_poll_interval_seconds', label: 'Funding Poll Interval (s)', type: 'number', min: 30, fallback: 60, tooltip: "Why it exists: defines how often the bot fetches fresh funding rates from Binance Futures /premiumIndex. One API call covers all 60 symbols. What changing it does: shorter = fresher data + more API weight (limit is 2400 requests/min); longer = staler funding signal. Default: 60s. Config key: funding_poll_interval_seconds" },
      { key: 'hedging_enabled', label: 'Hedging', type: 'bool', fallback: true, tooltip: "Why it exists: arbitrage holds spot crypto inventory between trades — without a hedge, that inventory is exposed to price drops. Continuous short-futures positions on Binance USDⓈ-M offset the spot exposure so profit comes only from arb spread, not price direction. What changing it does: ON = continuous delta-neutral hedging; OFF = unhedged spot exposure (riskier, simpler). Only the super-primary holds REAL futures positions; others always shadow-simulate. Default: ON. Config key: hedging_enabled" },
      { key: 'hedge_dust_threshold_usd', label: 'Hedge Dust Threshold ($)', type: 'number', min: 1, step: 1, fallback: 10.0, tooltip: "Why it exists: opening a hedge costs taker fee + funding, so tiny spot positions aren't worth hedging. This is the minimum spot notional that triggers a hedge. What changing it does: higher = ignores more small positions (less hedging activity, more unhedged exposure on small inventory); lower = hedges everything (more API churn for marginal positions). Default: $10. Config key: hedge_dust_threshold_usd" },
      { key: 'hedge_evaluation_interval_seconds', label: 'Hedge Eval Interval (s)', type: 'number', min: 30, fallback: 60, tooltip: "Why it exists: how often the hedge manager performs a periodic sanity check. Trades, transfers, expansions, and demotions also wake the hedge immediately. What changing it does: shorter = tighter fallback reconciliation; longer = fewer periodic checks. Default: 60s. Config key: hedge_evaluation_interval_seconds" },
      { key: 'hedge_leverage', label: 'Hedge Leverage', type: 'number', min: 1, max: 5, step: 1, fallback: 2, tooltip: "Why it exists: isolated USDⓈ-M leverage controls how much futures collateral is needed for the short hedge. 2x is the default compromise: lower futures reserve than 1x without the liquidation fragility of 3–5x. What changing it does: higher = less required free margin but more liquidation sensitivity; lower = safer but more capital locked in futures. Config key: hedge_leverage" },
      { key: 'hedge_margin_buffer_pct', label: 'Hedge Margin Buffer %', type: 'number', min: 0, max: 1, step: 0.05, fallback: 0.20, tooltip: "Why it exists: margin headroom required before opening a new hedge — available_balance must be ≥ (notional ÷ leverage) × (1 + buffer). Without a buffer, a small adverse price move could liquidate the futures position. What changing it does: higher = safer but blocks more hedge growth when margin is tight; lower = uses more margin. Default: 20%. Config key: hedge_margin_buffer_pct" },
      { key: 'hedge_adjust_threshold_pct', label: 'Hedge Adjust Threshold %', type: 'number', min: 0.01, max: 1, step: 0.01, fallback: 0.01, tooltip: "Why it exists: as spot inventory drifts, the hedge needs to grow/shrink to track. Adjusting on every microscopic change wastes futures taker fees, but a loose threshold leaves directional exposure. What changing it does: lower = tighter tracking; higher = less futures churn but more unhedged inventory. Default: 1%. Config key: hedge_adjust_threshold_pct" },
      { key: 'futures_capital_target_pct', label: 'Futures Reserve Target %', type: 'number', min: 0, max: 0.9, step: 0.01, fallback: 0.40, tooltip: "Why it exists: percentage of group capital reserved for Binance USDⓈ-M Futures collateral. Spot allocations use the remaining capital, so hedged P&L is realistic. Default: 40% at 2x. Config key: futures_capital_target_pct" },
      { key: 'futures_capital_topup_pct', label: 'Futures Top-Up %', type: 'number', min: 0, max: 0.9, step: 0.01, fallback: 0.35, tooltip: "Why it exists: live mode transfers USDT from Binance Spot to USDⓈ-M Futures when futures margin balance falls below this percentage. Default: 35%. Config key: futures_capital_topup_pct" },
      { key: 'futures_capital_emergency_pct', label: 'Futures Emergency %', type: 'number', min: 0, max: 0.9, step: 0.01, fallback: 0.30, tooltip: "Why it exists: when futures reserve falls below this percentage, new spot exposure is blocked because it may not be hedgeable. Default: 30%. Config key: futures_capital_emergency_pct" },
      { key: 'futures_capital_overflow_pct', label: 'Futures Overflow %', type: 'number', min: 0, max: 0.95, step: 0.01, fallback: 0.45, tooltip: "Why it exists: live mode can sweep idle futures excess back to Binance Spot when margin balance is above this percentage. Default: 45%. Config key: futures_capital_overflow_pct" },
      { key: 'futures_capital_transfer_min_usd', label: 'Futures Transfer Min ($)', type: 'number', min: 0, step: 1, fallback: 10.0, tooltip: "Why it exists: avoids dust transfers between Binance Spot and USDⓈ-M Futures. The live API key must have Universal Transfer permission. Default: $10. Config key: futures_capital_transfer_min_usd" },
    ],
  },
];

type ModalTab = 'general' | 'schedule' | 'fees';

export default function ConfigEditModal({
  configId,
  configName,
  groupName,
  isSuperPrimary,
  onClose,
  onSendMessage,
  onSendWithCallback,
  globalVolumes,
}: Props) {
  const toast = useToast();
  const [activeTab, setActiveTab] = useState<ModalTab>('general');
  const [name, setName] = useState(configName);
  const [description, setDescription] = useState('');
  const [settings, setSettings] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  // Fee Management tab dirty + save signal (mirror of FeeManagementTab state)
  const [feeDirty, setFeeDirty] = useState(false);
  const [feeSaveSignal, setFeeSaveSignal] = useState(0);

  // Esc closes
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Fetch current settings on open
  useEffect(() => {
    onSendWithCallback({ type: 'config_request_settings', config_id: configId }, (data) => {
      if (data && data.settings) {
        setSettings(data.settings);
        setName(data.name || configName);
        setDescription(data.description || '');
      }
      setLoading(false);
    });
  }, [configId, configName, onSendWithCallback]);

  const updateField = (key: string, value: any) => {
    setSettings((s) => (s ? { ...s, [key]: value } : s));
    setDirty(true);
  };

  const handleSave = () => {
    if (!settings) return;
    setSaving(true);
    if (name.trim() !== configName || description !== '' || dirty) {
      onSendMessage({
        type: 'config_rename',
        config_id: configId,
        name: name.trim() || configName,
        description,
      });
    }
    onSendMessage({
      type: 'config_apply_settings',
      config_id: configId,
      settings,
    });
    setDirty(false);
    toast.show(`Settings saved for ${configName}`, 'success');
    setTimeout(() => setSaving(false), 1500);
  };

  // Local fee_configs sub-handler so the embedded FeeManagementTab can save
  // back into THIS config's settings.fee_configs (not the global flat one).
  const feeConfigs: Record<string, ExchangeFeeConfig> | undefined = useMemo(() => {
    return settings?.fee_configs as Record<string, ExchangeFeeConfig> | undefined;
  }, [settings]);

  const handleFeeSendMessage = (msg: any) => {
    if (msg && msg.type === 'save_fee_settings' && msg.fee_configs) {
      // Update local settings + persist via per-config apply
      const next = { ...(settings ?? {}), fee_configs: msg.fee_configs };
      setSettings(next);
      onSendMessage({
        type: 'config_apply_settings',
        config_id: configId,
        settings: next,
      });
      toast.show(`Fee settings saved for ${configName}`, 'success');
    } else {
      onSendMessage(msg);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] bg-black/70 flex items-center justify-center p-4 sm:p-6"
      onClick={onClose}
    >
      <div
        className="bg-slate-900 border border-slate-700 rounded-lg shadow-2xl w-full max-w-[95vw] max-h-[95vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700 px-5 py-3 shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-base font-semibold text-white truncate">
              Edit Config:
            </span>
            <span className="text-base text-cyan-300 truncate">
              {groupName} / {configName}
            </span>
            {isSuperPrimary && (
              <span className="text-amber-400 text-xs font-bold ml-2">★★ SUPER</span>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white text-xl leading-none w-8 h-8 flex items-center justify-center rounded hover:bg-slate-800"
            title="Close (Esc)"
          >
            ×
          </button>
        </div>

        {/* Modal sub-tabs */}
        <div className="flex border-b border-slate-700 px-5 shrink-0">
          {([
            ['general', 'General'],
            ['schedule', 'Schedule (UTC)'],
            ['fees', 'Fee Management'],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
                activeTab === key
                  ? 'border-blue-500 text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Body — scrollable */}
        <div className="flex-1 overflow-y-auto p-5">
          {loading ? (
            <div className="text-center text-slate-400 py-8">Loading config…</div>
          ) : !settings ? (
            <div className="text-center text-rose-400 py-8">
              Failed to load config settings.
            </div>
          ) : activeTab === 'general' ? (
            <GeneralForm
              name={name}
              description={description}
              settings={settings}
              onNameChange={(v) => { setName(v); setDirty(true); }}
              onDescriptionChange={(v) => { setDescription(v); setDirty(true); }}
              onFieldChange={updateField}
            />
          ) : activeTab === 'schedule' ? (
            <ScheduleForm
              settings={settings}
              onFieldChange={updateField}
            />
          ) : (
            <FeeManagementTab
              feeConfigs={feeConfigs}
              feeRealMode={false}
              onSendMessage={handleFeeSendMessage}
              onSendWithCallback={onSendWithCallback}
              hideVolumeFetcher
              volumesGlobal={globalVolumes ?? null}
              hideInternalSaveButton
              saveSignal={feeSaveSignal}
              onDirtyChange={setFeeDirty}
            />
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end border-t border-slate-700 px-5 py-3 gap-3 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-md bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm"
          >
            Cancel
          </button>
          {(activeTab === 'general' || activeTab === 'schedule') ? (
            <button
              onClick={handleSave}
              disabled={!dirty || saving || loading || !settings}
              className={`px-4 py-1.5 rounded-md text-sm font-medium ${
                dirty && !saving
                  ? 'bg-blue-600 hover:bg-blue-500 text-white'
                  : 'bg-slate-800 text-slate-600 cursor-not-allowed'
              }`}
            >
              {saving ? 'Saving…' : 'Save Changes'}
            </button>
          ) : (
            <button
              onClick={() => setFeeSaveSignal((n) => n + 1)}
              disabled={!feeDirty}
              className={`px-4 py-1.5 rounded-md text-sm font-medium ${
                feeDirty
                  ? 'bg-blue-600 hover:bg-blue-500 text-white'
                  : 'bg-slate-800 text-slate-600 cursor-not-allowed'
              }`}
            >
              Save Fee Settings
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// Schedule tab: per-config UTC hour buckets (Strong/Neutral/Weak) +
// the gating multipliers/flags. Lets the operator design per-config
// market-regime windows. See SESSIONS.md analysis showing ~07/20-22
// UTC are the best arb hours and ~12-19 UTC are typically thin.
function ScheduleForm({
  settings,
  onFieldChange,
}: {
  settings: Record<string, any>;
  onFieldChange: (key: string, value: any) => void;
}) {
  const enabled: boolean = settings.regime_gating_enabled === true;
  const strongHours: Set<number> = new Set(
    (settings.regime_strong_hours as number[] | undefined) ?? []
  );
  const neutralHours: Set<number> = new Set(
    (settings.regime_neutral_hours as number[] | undefined) ?? []
  );
  // weak = anything not strong or neutral
  const weakCount = 24 - strongHours.size - neutralHours.size;

  // Click-cycle hour: weak → neutral → strong → weak
  const cycleHour = (h: number) => {
    const isStrong = strongHours.has(h);
    const isNeutral = neutralHours.has(h);
    const newStrong = new Set(strongHours);
    const newNeutral = new Set(neutralHours);
    if (isStrong) {
      newStrong.delete(h);  // strong → weak
    } else if (isNeutral) {
      newNeutral.delete(h);
      newStrong.add(h);     // neutral → strong
    } else {
      newNeutral.add(h);    // weak → neutral
    }
    onFieldChange('regime_strong_hours', Array.from(newStrong).sort((a, b) => a - b));
    onFieldChange('regime_neutral_hours', Array.from(newNeutral).sort((a, b) => a - b));
  };

  const setAll = (regime: 'strong' | 'neutral' | 'weak') => {
    if (regime === 'strong') {
      onFieldChange('regime_strong_hours', Array.from({ length: 24 }, (_, i) => i));
      onFieldChange('regime_neutral_hours', []);
    } else if (regime === 'neutral') {
      onFieldChange('regime_strong_hours', []);
      onFieldChange('regime_neutral_hours', Array.from({ length: 24 }, (_, i) => i));
    } else {
      onFieldChange('regime_strong_hours', []);
      onFieldChange('regime_neutral_hours', []);
    }
  };

  const HOUR_NOTES: Record<number, string> = {
    7: 'Pre-London (good)',
    15: 'NY+EU overlap (good)',
    20: 'NY winding down (good)',
    21: 'Late US (good)',
    22: 'Late US (good)',
    10: 'Dead',
    12: 'London lunch (dead)',
    13: 'NY pre-open (dead)',
    14: 'NY pre-open (dead)',
    16: 'Mid-day lull',
    17: 'NY peak (thin spreads)',
    18: 'NY peak (thin spreads)',
    19: 'NY peak (thin spreads)',
  };

  return (
    <div className="space-y-6">
      <section className="bg-slate-800/40 rounded-lg p-4">
        <div className="flex items-start justify-between gap-3 mb-2">
          <div>
            <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Time-Based Regime Gating</h3>
            <p className="text-xs text-slate-500 mt-1">
              Each UTC hour is one of three regimes: STRONG, NEUTRAL, or WEAK. STRONG/NEUTRAL trade normally; WEAK applies the multipliers/gates below to suppress fee-burning activity during thin-spread windows. Click an hour to cycle: weak → neutral → strong → weak.
            </p>
          </div>
          <label className="flex items-center gap-2 shrink-0">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => onFieldChange('regime_gating_enabled', e.target.checked)}
              className="w-4 h-4 accent-blue-500"
            />
            <span className="text-sm text-slate-300">Enabled</span>
          </label>
        </div>

        {/* 24-hour grid */}
        {/* 24 columns on desktop, 12 on mobile (so 2 rows of 12) */}
        <div className="grid grid-cols-12 sm:grid-cols-[repeat(24,minmax(0,1fr))] gap-1 mt-4 mb-2">
          {Array.from({ length: 24 }, (_, h) => {
            const isStrong = strongHours.has(h);
            const isNeutral = neutralHours.has(h);
            const cls = isStrong
              ? 'bg-emerald-600 hover:bg-emerald-500 text-white border-emerald-400'
              : isNeutral
                ? 'bg-amber-600/70 hover:bg-amber-500 text-white border-amber-400'
                : 'bg-slate-700/60 hover:bg-slate-600 text-slate-300 border-slate-600';
            const note = HOUR_NOTES[h];
            return (
              <button
                key={h}
                type="button"
                disabled={!enabled}
                onClick={() => cycleHour(h)}
                title={note ? `${h.toString().padStart(2, '0')}:00 — ${note}` : `${h.toString().padStart(2, '0')}:00`}
                className={`px-1 py-2 rounded border text-xs font-mono transition-colors ${cls} ${
                  !enabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'
                }`}
              >
                {h.toString().padStart(2, '0')}
              </button>
            );
          })}
        </div>

        {/* Counts + bulk buttons */}
        <div className="flex items-center justify-between mt-3">
          <div className="text-xs text-slate-400 space-x-3">
            <span><span className="inline-block w-3 h-3 align-middle bg-emerald-600 rounded-sm mr-1"></span>STRONG: {strongHours.size}</span>
            <span><span className="inline-block w-3 h-3 align-middle bg-amber-600/70 rounded-sm mr-1"></span>NEUTRAL: {neutralHours.size}</span>
            <span><span className="inline-block w-3 h-3 align-middle bg-slate-700 rounded-sm mr-1"></span>WEAK: {weakCount}</span>
          </div>
          <div className="flex gap-2">
            <button type="button" disabled={!enabled} onClick={() => setAll('strong')} className="px-2 py-1 text-xs rounded bg-emerald-700/60 hover:bg-emerald-600/60 text-white disabled:opacity-40 disabled:cursor-not-allowed">All Strong</button>
            <button type="button" disabled={!enabled} onClick={() => setAll('neutral')} className="px-2 py-1 text-xs rounded bg-amber-700/60 hover:bg-amber-600/60 text-white disabled:opacity-40 disabled:cursor-not-allowed">All Neutral</button>
            <button type="button" disabled={!enabled} onClick={() => setAll('weak')} className="px-2 py-1 text-xs rounded bg-slate-700 hover:bg-slate-600 text-white disabled:opacity-40 disabled:cursor-not-allowed">All Weak</button>
          </div>
        </div>

        <p className="text-[11px] text-slate-500 mt-3">
          Hover an hour to see why it's typical-good or typical-thin (based on the 9-day Session #19 analysis). Best arb hours: 07, 15, 20-22 UTC (asynchronous market handovers). Worst: 10, 12-14, 16-19 UTC (high competition / mid-day liquidity).
        </p>
      </section>

      {/* WEAK-regime behavior settings */}
      <section className="bg-slate-800/40 rounded-lg p-4">
        <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-3">Weak-Regime Gates</h3>
        <p className="text-xs text-slate-500 mb-4">These take effect ONLY during WEAK hours (above). During STRONG/NEUTRAL hours, the bot trades normally regardless of these settings.</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-slate-500 mb-1">Min Net Profit Multiplier ×</label>
            <input
              type="number"
              min={1}
              max={10}
              step={0.1}
              value={settings.regime_weak_min_net_multiplier ?? 2.0}
              onChange={(e) => onFieldChange('regime_weak_min_net_multiplier', Number(e.target.value))}
              className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-sm text-white"
              disabled={!enabled}
            />
            <p className="text-[11px] text-slate-500 mt-1">During weak hours, base min_net_profit_pct × this. 2.0 = require 2× spread to trade. Higher = more selective. Default: 2.0</p>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Rebalance Policy</label>
            <select
              value={settings.regime_weak_rebalance_policy ?? (settings.regime_weak_disable_rebalance ? 'strict' : 'off')}
              onChange={(e) => {
                const policy = e.target.value;
                onFieldChange('regime_weak_rebalance_policy', policy);
                onFieldChange('regime_weak_disable_rebalance', policy !== 'off');
              }}
              className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-sm text-white"
              disabled={!enabled}
            >
              <option value="refill_only">Refill only</option>
              <option value="strict">Strict block</option>
              <option value="off">Off</option>
            </select>
            <p className="text-[11px] text-slate-500 mt-1">Refill only allows local/cheap inventory refills during weak hours but still blocks expensive rebalances. Strict blocks all weak-hour rebalances. Off uses normal gates. Default: refill_only.</p>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Refill Max External Fee ($)</label>
            <input
              type="number"
              min={0}
              max={100}
              step={0.01}
              value={settings.regime_weak_refill_max_fee_usd ?? 0.10}
              onChange={(e) => onFieldChange('regime_weak_refill_max_fee_usd', Number(e.target.value))}
              className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-sm text-white"
              disabled={!enabled || (settings.regime_weak_rebalance_policy ?? 'refill_only') !== 'refill_only'}
            />
            <p className="text-[11px] text-slate-500 mt-1">External transfers above this fee stay blocked in weak hours. Internal buy/sell refills are still allowed. Default: $0.10.</p>
          </div>
          <div className="flex flex-col justify-center gap-2 md:col-span-2">
            {[
              ['regime_weak_disable_demote', 'Disable Demote', 'Skip demotions during weak hours — keeps held inventory in place rather than paying teardown fees during low-volume windows.'],
              ['regime_weak_disable_expand', 'Disable Expand', 'Skip auto-expand-on-understaff during weak hours. Don\'t pay setup fees when the window won\'t produce enough trades to amortize them.'],
            ].map(([key, label, hint]) => (
              <label key={key} className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={settings[key] === true}
                  onChange={(e) => onFieldChange(key, e.target.checked)}
                  className="mt-1 w-4 h-4 accent-blue-500"
                  disabled={!enabled}
                />
                <span>
                  <span className="text-slate-200">{label}</span>
                  <span className="block text-[11px] text-slate-500">{hint}</span>
                </span>
              </label>
            ))}
          </div>
        </div>
      </section>

      {/* Anti-churn settings (apply to all hours) */}
      <section className="bg-slate-800/40 rounded-lg p-4">
        <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-3">Anti-Churn (apply to all hours)</h3>
        <p className="text-xs text-slate-500 mb-4">These three protections apply at all hours, complementing regime gating. They prevent the activate→demote→reactivate cycle that bleeds transfer fees.</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs text-slate-500 mb-1">Quiet-Period Pause (min)</label>
            <input
              type="number"
              min={0}
              max={240}
              step={1}
              value={settings.quiet_period_pause_minutes ?? 0}
              onChange={(e) => onFieldChange('quiet_period_pause_minutes', Number(e.target.value))}
              className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-sm text-white"
            />
            <p className="text-[11px] text-slate-500 mt-1">After this many minutes without a trade, suppress rebalance/replenish/overflow logic. 0 = disabled. Resets on first trade. Default: 30 (Maximize Profits).</p>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Activation Profit Horizon ×</label>
            <input
              type="number"
              min={1}
              max={10}
              step={0.1}
              value={settings.activation_profit_horizon_multiplier ?? 2.0}
              onChange={(e) => onFieldChange('activation_profit_horizon_multiplier', Number(e.target.value))}
              className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-sm text-white"
            />
            <p className="text-[11px] text-slate-500 mt-1">Setup cost must clear est_hourly_profit × reallocation_cost_horizon × this. Higher = stricter activations (rejects marginal symbols). Default: 2.0 (legacy), Maximize Profits uses 4.0.</p>
          </div>
          <div className="flex items-center">
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={settings.demotion_freq_scaling_enabled !== false}
                onChange={(e) => onFieldChange('demotion_freq_scaling_enabled', e.target.checked)}
                className="mt-1 w-4 h-4 accent-blue-500"
              />
              <span>
                <span className="text-slate-200">Demotion-Freq Cooldown Scaling</span>
                <span className="block text-[11px] text-slate-500">A symbol that demotes repeatedly gets exponentially longer cooldown (1×/2×/4×/8× for 1/2/3/4+ demotions in 24h). Self-locks problem symbols. Recommended ON.</span>
              </span>
            </label>
          </div>
        </div>
      </section>
    </div>
  );
}

function GeneralForm({
  name,
  description,
  settings,
  onNameChange,
  onDescriptionChange,
  onFieldChange,
}: {
  name: string;
  description: string;
  settings: Record<string, any>;
  onNameChange: (v: string) => void;
  onDescriptionChange: (v: string) => void;
  onFieldChange: (key: string, value: any) => void;
}) {
  return (
    <div className="space-y-6">
      {/* Identity */}
      <section className="bg-slate-800/40 rounded-lg p-4">
        <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-3">Identity</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-slate-500 mb-1">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => onNameChange(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">
              Description
              <span className="text-slate-600 ml-2 italic">(why did you create this config?)</span>
            </label>
            <textarea
              rows={1}
              value={description}
              onChange={(e) => onDescriptionChange(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none resize-none"
              placeholder="What hypothesis are you testing?"
            />
          </div>
        </div>
      </section>

      {/* Settings sections */}
      {SECTIONS.map((section) => (
        <section key={section.title} className="bg-slate-800/40 rounded-lg p-4">
          <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-3">
            {section.title}
          </h3>
          {/* 2 columns on wide screens (sm = 640px+), single column on narrow */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
            {section.fields.map((f) => {
              const val = settings[f.key];
              // pct: stored as fraction (0.04), displayed as 4
              const isPct = f.type === 'pct';
              const displayVal = isPct
                ? Number((((val ?? f.fallback) as number) * 100).toFixed(4))
                : val ?? f.fallback;
              return (
                <div key={f.key}>
                  <label className="flex items-center flex-wrap text-xs text-slate-500 mb-1">
                    <span>{f.label}</span>
                    <span className="ml-1.5 text-slate-600 font-mono text-[10px]">
                      ({f.key})
                    </span>
                    {f.tooltip && <Tooltip text={f.tooltip} />}
                  </label>
                  {f.type === 'bool' ? (
                    <label className="flex items-center gap-2 cursor-pointer h-9">
                      <input
                        type="checkbox"
                        checked={val ?? f.fallback}
                        onChange={(e) => onFieldChange(f.key, e.target.checked)}
                        className="accent-blue-500 w-4 h-4"
                      />
                      <span className="text-sm text-slate-300">
                        {val ?? f.fallback ? 'Enabled' : 'Disabled'}
                      </span>
                    </label>
                  ) : isPct ? (
                    <div className="relative">
                      <input
                        type="number"
                        value={displayVal}
                        min={f.min}
                        max={f.max}
                        step={f.step ?? 0.1}
                        onChange={(e) => {
                          const n = Number(e.target.value);
                          if (Number.isNaN(n)) {
                            onFieldChange(f.key, f.fallback);
                          } else {
                            // Display as %, store as fraction
                            onFieldChange(f.key, n / 100);
                          }
                        }}
                        className="w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-1.5 pr-8 text-sm text-white focus:border-blue-500 focus:outline-none"
                      />
                      <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 text-sm pointer-events-none">%</span>
                    </div>
                  ) : (
                    <input
                      type="number"
                      value={displayVal}
                      min={f.min}
                      max={f.max}
                      step={f.step ?? 1}
                      onChange={(e) => {
                        const n = Number(e.target.value);
                        onFieldChange(f.key, Number.isNaN(n) ? f.fallback : n);
                      }}
                      className="w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
                    />
                  )}
                </div>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
