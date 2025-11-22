"""
Backtest Analysis Module
Comprehensive temporal, seasonal, and performance analysis for backtest results.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
from collections import defaultdict


def analyze_monthly_performance(trades: List[Dict]) -> Dict:
    """
    Analyze performance metrics grouped by month.
    
    Args:
        trades: List of trade dictionaries with 'entry_time', 'pnl', etc.
    
    Returns:
        Dictionary with monthly performance metrics:
        {
            '2024-01': {
                'trades': 5,
                'win_rate': 60.0,
                'total_pnl': 15000.0,
                'avg_pnl': 3000.0,
                'return_pct': 15.0,
                'winning_trades': 3,
                'losing_trades': 2,
                'max_win': 5000.0,
                'max_loss': -2000.0
            },
            ...
        }
    """
    if not trades:
        return {}
    
    df = pd.DataFrame(trades)
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    df['month_key'] = df['entry_time'].dt.to_period('M').astype(str)
    
    monthly_stats = {}
    
    for month_key, month_trades in df.groupby('month_key'):
        month_df = month_trades.copy()
        total_trades = len(month_df)
        winning_trades = len(month_df[month_df['pnl'] > 0])
        losing_trades = len(month_df[month_df['pnl'] < 0])
        total_pnl = float(month_df['pnl'].sum())
        avg_pnl = float(month_df['pnl'].mean()) if total_trades > 0 else 0.0
        win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0
        
        # Calculate return percentage (assuming we track initial capital per month)
        # For simplicity, we'll use avg_pnl as a proxy, but this could be enhanced
        # with actual capital tracking
        winning_pnl = month_df[month_df['pnl'] > 0]['pnl'].sum() if winning_trades > 0 else 0.0
        losing_pnl = abs(month_df[month_df['pnl'] < 0]['pnl'].sum()) if losing_trades > 0 else 0.0
        
        max_win = float(month_df['pnl'].max()) if total_trades > 0 else 0.0
        max_loss = float(month_df['pnl'].min()) if total_trades > 0 else 0.0
        
        monthly_stats[month_key] = {
            'trades': total_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'return_pct': avg_pnl,  # Simplified - could be enhanced with capital tracking
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'max_win': max_win,
            'max_loss': max_loss,
            'winning_pnl': float(winning_pnl),
            'losing_pnl': float(losing_pnl)
        }
    
    return monthly_stats


def analyze_quarterly_performance(trades: List[Dict]) -> Dict:
    """
    Analyze performance metrics grouped by quarter.
    
    Args:
        trades: List of trade dictionaries
    
    Returns:
        Dictionary with quarterly performance metrics
    """
    if not trades:
        return {}
    
    df = pd.DataFrame(trades)
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    df['quarter'] = df['entry_time'].dt.to_period('Q').astype(str)
    
    quarterly_stats = {}
    
    for quarter, quarter_trades in df.groupby('quarter'):
        quarter_df = quarter_trades.copy()
        total_trades = len(quarter_df)
        winning_trades = len(quarter_df[quarter_df['pnl'] > 0])
        losing_trades = len(quarter_df[quarter_df['pnl'] < 0])
        total_pnl = float(quarter_df['pnl'].sum())
        avg_pnl = float(quarter_df['pnl'].mean()) if total_trades > 0 else 0.0
        win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0
        
        quarterly_stats[quarter] = {
            'trades': total_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades
        }
    
    return quarterly_stats


def analyze_yearly_performance(trades: List[Dict]) -> Dict:
    """
    Analyze performance metrics grouped by year.
    
    Args:
        trades: List of trade dictionaries
    
    Returns:
        Dictionary with yearly performance metrics
    """
    if not trades:
        return {}
    
    df = pd.DataFrame(trades)
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    df['year'] = df['entry_time'].dt.year
    
    yearly_stats = {}
    
    for year, year_trades in df.groupby('year'):
        year_df = year_trades.copy()
        total_trades = len(year_df)
        winning_trades = len(year_df[year_df['pnl'] > 0])
        losing_trades = len(year_df[year_df['pnl'] < 0])
        total_pnl = float(year_df['pnl'].sum())
        avg_pnl = float(year_df['pnl'].mean()) if total_trades > 0 else 0.0
        win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0
        
        yearly_stats[str(year)] = {
            'trades': total_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades
        }
    
    return yearly_stats


def detect_seasonal_patterns(trades: List[Dict]) -> Dict:
    """
    Detect seasonal patterns and identify best/worst months for trading.
    
    Args:
        trades: List of trade dictionaries
    
    Returns:
        Dictionary with seasonal insights and recommendations:
        {
            'best_months': ['March', 'October', 'November'],
            'worst_months': ['May', 'June', 'August'],
            'avoid_months': ['May'],
            'ideal_months': ['March', 'October'],
            'month_rankings': {...}
        }
    """
    if not trades:
        return {
            'best_months': [],
            'worst_months': [],
            'avoid_months': [],
            'ideal_months': [],
            'month_rankings': {}
        }
    
    monthly_stats = analyze_monthly_performance(trades)
    
    if not monthly_stats:
        return {
            'best_months': [],
            'worst_months': [],
            'avoid_months': [],
            'ideal_months': [],
            'month_rankings': {}
        }
    
    # Month name mapping
    month_names = {
        '01': 'January', '02': 'February', '03': 'March', '04': 'April',
        '05': 'May', '06': 'June', '07': 'July', '08': 'August',
        '09': 'September', '10': 'October', '11': 'November', '12': 'December'
    }
    
    # Aggregate by month number (across all years)
    month_aggregates = defaultdict(lambda: {'total_pnl': 0.0, 'total_trades': 0, 'win_rate_sum': 0.0, 'count': 0})
    
    for month_key, stats in monthly_stats.items():
        # Extract month number from 'YYYY-MM' format
        month_num = month_key.split('-')[1]
        month_aggregates[month_num]['total_pnl'] += stats['total_pnl']
        month_aggregates[month_num]['total_trades'] += stats['trades']
        month_aggregates[month_num]['win_rate_sum'] += stats['win_rate']
        month_aggregates[month_num]['count'] += 1
    
    # Calculate averages
    month_rankings = {}
    for month_num, agg in month_aggregates.items():
        avg_pnl = agg['total_pnl'] / agg['count'] if agg['count'] > 0 else 0.0
        avg_win_rate = agg['win_rate_sum'] / agg['count'] if agg['count'] > 0 else 0.0
        month_rankings[month_num] = {
            'month_name': month_names[month_num],
            'avg_pnl': avg_pnl,
            'avg_win_rate': avg_win_rate,
            'total_trades': agg['total_trades'],
            'total_pnl': agg['total_pnl']
        }
    
    # Sort by average P&L
    sorted_by_pnl = sorted(month_rankings.items(), key=lambda x: x[1]['avg_pnl'], reverse=True)
    
    # Get top 3 and bottom 3 months
    best_months = [month_rankings[m]['month_name'] for m, _ in sorted_by_pnl[:3] if month_rankings[m]['total_trades'] >= 3]
    worst_months = [month_rankings[m]['month_name'] for m, _ in sorted_by_pnl[-3:] if month_rankings[m]['total_trades'] >= 3]
    
    # Identify months to avoid (negative returns + low win rate)
    avoid_months = []
    for month_num, stats in month_rankings.items():
        if stats['avg_pnl'] < 0 and stats['avg_win_rate'] < 50.0 and stats['total_trades'] >= 3:
            avoid_months.append(stats['month_name'])
    
    # Identify ideal months (high returns + high win rate)
    ideal_months = []
    for month_num, stats in month_rankings.items():
        if stats['avg_pnl'] > 0 and stats['avg_win_rate'] >= 55.0 and stats['total_trades'] >= 3:
            ideal_months.append(stats['month_name'])
    
    return {
        'best_months': best_months,
        'worst_months': worst_months,
        'avoid_months': avoid_months,
        'ideal_months': ideal_months,
        'month_rankings': {month_names[k]: v for k, v in month_rankings.items()}
    }


def analyze_by_direction(trades: List[Dict]) -> Dict:
    """
    Analyze performance by direction (CE vs PE).
    
    Args:
        trades: List of trade dictionaries with 'direction' field
    
    Returns:
        Dictionary with direction-based analysis:
        {
            'CE': {
                'trades': 50,
                'win_rate': 60.0,
                'total_pnl': 50000.0,
                'avg_pnl': 1000.0
            },
            'PE': {...},
            'monthly_breakdown': {
                '2024-01': {'CE': {...}, 'PE': {...}},
                ...
            }
        }
    """
    if not trades:
        return {'CE': {}, 'PE': {}, 'monthly_breakdown': {}}
    
    df = pd.DataFrame(trades)
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    df['month_key'] = df['entry_time'].dt.to_period('M').astype(str)
    
    # Overall direction stats
    direction_stats = {}
    for direction in ['CE', 'PE']:
        dir_trades = df[df['direction'] == direction]
        if len(dir_trades) > 0:
            total_trades = len(dir_trades)
            winning_trades = len(dir_trades[dir_trades['pnl'] > 0])
            total_pnl = float(dir_trades['pnl'].sum())
            avg_pnl = float(dir_trades['pnl'].mean())
            win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0
            
            direction_stats[direction] = {
                'trades': total_trades,
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'avg_pnl': avg_pnl,
                'winning_trades': winning_trades,
                'losing_trades': total_trades - winning_trades
            }
        else:
            direction_stats[direction] = {
                'trades': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'avg_pnl': 0.0,
                'winning_trades': 0,
                'losing_trades': 0
            }
    
    # Monthly breakdown by direction
    monthly_breakdown = {}
    for month_key, month_trades in df.groupby('month_key'):
        month_breakdown = {}
        for direction in ['CE', 'PE']:
            dir_trades = month_trades[month_trades['direction'] == direction]
            if len(dir_trades) > 0:
                total_trades = len(dir_trades)
                winning_trades = len(dir_trades[dir_trades['pnl'] > 0])
                total_pnl = float(dir_trades['pnl'].sum())
                avg_pnl = float(dir_trades['pnl'].mean())
                win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0
                
                month_breakdown[direction] = {
                    'trades': total_trades,
                    'win_rate': win_rate,
                    'total_pnl': total_pnl,
                    'avg_pnl': avg_pnl
                }
            else:
                month_breakdown[direction] = {
                    'trades': 0,
                    'win_rate': 0.0,
                    'total_pnl': 0.0,
                    'avg_pnl': 0.0
                }
        monthly_breakdown[month_key] = month_breakdown
    
    return {
        'CE': direction_stats.get('CE', {}),
        'PE': direction_stats.get('PE', {}),
        'monthly_breakdown': monthly_breakdown
    }


def analyze_by_strike_selection(trades: List[Dict], spot_data: Optional[pd.DataFrame] = None) -> Dict:
    """
    Analyze performance by strike selection (ATM, ITM, OTM).
    Note: This requires spot price data to determine if strike is ATM/ITM/OTM.
    
    Args:
        trades: List of trade dictionaries with 'strike' field
        spot_data: Optional DataFrame with spot prices indexed by timestamp
    
    Returns:
        Dictionary with strike selection analysis
    """
    if not trades:
        return {}
    
    df = pd.DataFrame(trades)
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    
    # If spot data is available, classify strikes
    if spot_data is not None and len(spot_data) > 0:
        # This would require matching entry_time with spot prices
        # For now, we'll use a simplified approach based on strike distribution
        pass
    
    # Simplified: Group by strike ranges (this could be enhanced)
    strike_stats = {}
    
    # Calculate strike statistics
    if 'strike' in df.columns:
        strikes = df['strike'].values
        strike_mean = np.mean(strikes) if len(strikes) > 0 else 0
        
        # Classify as ATM (within 2% of mean), ITM (below), OTM (above)
        for idx, row in df.iterrows():
            strike = row['strike']
            pnl = row['pnl']
            
            if abs(strike - strike_mean) / strike_mean < 0.02:
                category = 'ATM'
            elif strike < strike_mean:
                category = 'ITM'
            else:
                category = 'OTM'
            
            if category not in strike_stats:
                strike_stats[category] = {'trades': 0, 'total_pnl': 0.0, 'winning_trades': 0}
            
            strike_stats[category]['trades'] += 1
            strike_stats[category]['total_pnl'] += pnl
            if pnl > 0:
                strike_stats[category]['winning_trades'] += 1
        
        # Calculate metrics
        for category in strike_stats:
            stats = strike_stats[category]
            stats['avg_pnl'] = stats['total_pnl'] / stats['trades'] if stats['trades'] > 0 else 0.0
            stats['win_rate'] = (stats['winning_trades'] / stats['trades'] * 100.0) if stats['trades'] > 0 else 0.0
    
    return strike_stats


def analyze_volatility_performance(trades: List[Dict], spot_data: Optional[pd.DataFrame] = None) -> Dict:
    """
    Analyze performance correlation with volatility.
    
    Args:
        trades: List of trade dictionaries
        spot_data: Optional DataFrame with spot prices for volatility calculation
    
    Returns:
        Dictionary with volatility analysis
    """
    if not trades or spot_data is None or len(spot_data) == 0:
        return {}
    
    df = pd.DataFrame(trades)
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    
    # Calculate realized volatility for each trade period
    # This is a simplified version - could be enhanced with proper volatility calculation
    volatility_stats = {
        'high_volatility': {'trades': 0, 'total_pnl': 0.0, 'win_rate': 0.0},
        'medium_volatility': {'trades': 0, 'total_pnl': 0.0, 'win_rate': 0.0},
        'low_volatility': {'trades': 0, 'total_pnl': 0.0, 'win_rate': 0.0}
    }
    
    # Simplified volatility classification (would need proper calculation)
    # For now, return empty structure
    return volatility_stats


def analyze_drawdowns_by_period(equity_curve_dates: List[Dict]) -> Dict:
    """
    Analyze drawdowns by time period.
    
    Args:
        equity_curve_dates: List of dictionaries with 'date', 'capital', 'trade_num'
    
    Returns:
        Dictionary with drawdown analysis by period
    """
    if not equity_curve_dates or len(equity_curve_dates) < 2:
        return {}
    
    df = pd.DataFrame(equity_curve_dates)
    df['date'] = pd.to_datetime(df['date'])
    df['month_key'] = df['date'].dt.to_period('M').astype(str)
    
    # Calculate drawdowns
    df = df.sort_values('date')
    df['running_max'] = df['capital'].cummax()
    df['drawdown'] = ((df['capital'] - df['running_max']) / df['running_max'] * 100.0)
    
    # Monthly drawdown stats
    monthly_drawdowns = {}
    for month_key, month_data in df.groupby('month_key'):
        max_dd = float(month_data['drawdown'].min())
        avg_dd = float(month_data['drawdown'].mean())
        monthly_drawdowns[month_key] = {
            'max_drawdown': max_dd,
            'avg_drawdown': avg_dd
        }
    
    return {
        'monthly_drawdowns': monthly_drawdowns,
        'max_drawdown_overall': float(df['drawdown'].min()),
        'drawdown_data': df[['date', 'capital', 'drawdown']].to_dict('records')
    }


def calculate_risk_metrics(trades: List[Dict], equity_curve: List[float], risk_free_rate: float = 0.0) -> Dict:
    """
    Calculate risk-adjusted metrics (Sharpe, Sortino, Calmar ratios).
    
    Args:
        trades: List of trade dictionaries
        equity_curve: List of capital values over time
        risk_free_rate: Risk-free rate (default 0.0 for simplicity)
    
    Returns:
        Dictionary with risk metrics
    """
    if not trades or len(equity_curve) < 2:
        return {
            'sharpe_ratio': 0.0,
            'sortino_ratio': 0.0,
            'calmar_ratio': 0.0
        }
    
    df = pd.DataFrame(trades)
    
    # Calculate returns
    returns = df['pnl'].values
    
    if len(returns) == 0 or np.std(returns) == 0:
        return {
            'sharpe_ratio': 0.0,
            'sortino_ratio': 0.0,
            'calmar_ratio': 0.0
        }
    
    # Sharpe Ratio
    mean_return = np.mean(returns)
    std_return = np.std(returns)
    sharpe_ratio = (mean_return - risk_free_rate) / std_return if std_return > 0 else 0.0
    
    # Sortino Ratio (only downside deviation)
    downside_returns = returns[returns < 0]
    downside_std = np.std(downside_returns) if len(downside_returns) > 0 else 0.0
    sortino_ratio = (mean_return - risk_free_rate) / downside_std if downside_std > 0 else 0.0
    
    # Calmar Ratio (return / max drawdown)
    equity_array = np.array(equity_curve)
    running_max = np.maximum.accumulate(equity_array)
    drawdowns = (equity_array - running_max) / running_max
    max_drawdown = abs(np.min(drawdowns)) if len(drawdowns) > 0 else 1.0
    
    total_return = (equity_curve[-1] - equity_curve[0]) / equity_curve[0] if equity_curve[0] > 0 else 0.0
    calmar_ratio = total_return / max_drawdown if max_drawdown > 0 else 0.0
    
    return {
        'sharpe_ratio': float(sharpe_ratio),
        'sortino_ratio': float(sortino_ratio),
        'calmar_ratio': float(calmar_ratio),
        'max_drawdown': float(max_drawdown * 100.0),  # As percentage
        'total_return': float(total_return * 100.0)  # As percentage
    }


def analyze_trade_distribution(trades: List[Dict]) -> Dict:
    """
    Analyze trade distribution by day of week, hour, etc.
    
    Args:
        trades: List of trade dictionaries
    
    Returns:
        Dictionary with trade distribution analysis
    """
    if not trades:
        return {}
    
    df = pd.DataFrame(trades)
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    df['day_of_week'] = df['entry_time'].dt.day_name()
    df['hour'] = df['entry_time'].dt.hour
    df['month'] = df['entry_time'].dt.month
    
    # Day of week distribution
    dow_dist = df['day_of_week'].value_counts().to_dict()
    
    # Hour distribution
    hour_dist = df['hour'].value_counts().to_dict()
    
    # Month distribution
    month_dist = df['month'].value_counts().to_dict()
    
    return {
        'day_of_week': dow_dist,
        'hour': hour_dist,
        'month': month_dist,
        'total_trades': len(df)
    }

