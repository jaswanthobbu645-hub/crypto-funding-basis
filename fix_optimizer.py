import sys

# Read the file
with open(r'C:\users\Avinash\crypto_backtest\07_parameter_optimizer.py', 'r') as f:
    lines = f.readlines()

# First patch: after "df = df.copy()"
for i, line in enumerate(lines):
    if line.strip() == "df = df.copy()":
        # Insert after this line
        lines.insert(i+1, "        # Calculate total time days for annualization and trades per month\n")
        lines.insert(i+2, "        if len(df) > 1:\n")
        lines.insert(i+3, "            total_time_days = (df.index[-1] - df.index[0]).days\n")
        lines.insert(i+4, "        else:\n")
        lines.insert(i+5, "            total_time_days = 0\n")
        break

# Second patch: replace the Sharpe section
# Find the line: "# Sharpe ratio: approximate using trade returns"
start = -1
end = -1
for i, line in enumerate(lines):
    if line.strip() == "# Sharpe ratio: approximate using trade returns":
        start = i
    if start != -1 and line.strip() == "else:" and i+1 < len(lines) and lines[i+1].strip() == "sharpe_ratio = 0":
        end = i+1  # we want to replace until the end of the else block (the line after else:)
        break

if start != -1 and end != -1:
    # Replace lines[start:end+1] with our new block
    new_block = [
        "        # Sharpe ratio: approximate using trade returns\n",
        "        if len(trades_df) > 1:\n",
        "            # Calculate the return per trade on the initial equity (approximation)\n",
        "            returns = trades_df['net_pnl'] / initial_equity\n",
        "            # Annualize assuming trades occur uniformly over the period\n",
        "            # We approximate the number of trades per year from the time range\n",
        "            total_time_years = total_time_days / 365.25 if total_time_days > 0 else 1\n",
        "            trades_per_year = total_trades / total_time_years if total_time_years > 0 else total_trades\n",
        "            sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(trades_per_year) if np.std(returns) > 0 else 0\n",
        "        else:\n",
        "            sharpe_ratio = 0\n"
    ]
    # Remove the old lines and insert the new ones
    del lines[start:end+1]
    for j, new_line in enumerate(new_block):
        lines.insert(start+j, new_line)

# Third patch: in the else block (no trades) we need to set trades_per_month = 0.0
# We'll find the else block for no trades (the one that sets net_pnl=0.0, etc.) and add the line after net_pnl_pct = 0.0
in_no_trades_else = False
for i, line in enumerate(lines):
    if line.strip() == "else:" and i>0 and lines[i-1].strip() == "if trades:":
        in_no_trades_else = True
    if in_no_trades_else and line.strip() == "net_pnl_pct = 0.0":
        # Insert after this line
        lines.insert(i+1, "        trades_per_month = 0.0\n")
        break

# Write back
with open(r'C:\users\Avinash\crypto_backtest\07_parameter_optimizer.py', 'w') as f:
    f.writelines(lines)

print("Fix applied.")
