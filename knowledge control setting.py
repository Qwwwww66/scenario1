import pandas as pd

# Load the uploaded Excel file
file_path = "data/test flow1.xlsx"
df = pd.read_excel(file_path)

# Define basic rule-based logic for a junior engineer:
# - When flow is low (< 20000): lower DO and IMLR
# - When flow is medium (20000–40000): normal DO and IMLR
# - When flow is high (> 40000): higher DO and IMLR
def assign_controls(flow):
    if flow < 20000:
        return 1.5, 20000   # low DO, low IMLR
    elif flow < 40000:
        return 2.0, 30000   # medium DO, medium IMLR
    else:
        return 3.0, 40000   # high DO, high IMLR

# Apply the rule to each row
df[['DO_Setpoint', 'IMLR_Setpoint']] = df['Influent Flow Rate (m3/d)'].apply(lambda x: pd.Series(assign_controls(x)))

# Save the updated DataFrame to Excel
output_file_path = "data/rule_based_control_settings_flow1.xlsx"
df.to_excel(output_file_path, index=False)
