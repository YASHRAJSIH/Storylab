import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import os
import re

# --- INTERPRETATION LOGIC ---
def interpret_generic_file(text, topic_name):
    paragraphs = re.findall(r"Paragraph \d+ \((.*?)\):", text)
    if len(paragraphs) >= 3:
        labels = [
            f"{paragraphs[0]} (2020)",
            f"{paragraphs[1]} (2024)",
            f"{paragraphs[2]} (2040)"
        ]
    else:
        labels = [f"{topic_name} (2020)", f"{topic_name} (2024)", f"{topic_name} (2040)"]

    topic_lower = topic_name.lower()
    if "energy" in topic_lower:
        past = re.findall(r"(-?\d+\.\d+)", text.split("Paragraph 1")[1].split("Paragraph 2")[0])
        past_sum = sum(float(v) for v in past)
        planned = re.search(r"1\.5\s*GW", text)
        target = re.search(r"2\.4\s*GW", text)
        planned_val = 1.5 if planned else 0.0
        target_val = 2.4 if target else planned_val
        values = [past_sum, 0.0, planned_val, target_val]
        labels = [f"{paragraphs[0]} (2020)", f"{paragraphs[1]} (2024)", "Planned (2030)", f"{paragraphs[2]} Target (2040)"]
    elif "finance" in topic_lower:
        values = [0.5, -1.0, -0.8]
    elif "construction" in topic_lower:
        values = [-1.0, -0.5, -0.7]
    elif "economic" in topic_lower:
        values = [-1.5, 0.5, 0.2]
    elif "industry" in topic_lower:
        values = [-0.8, -0.3, -0.6]
    elif "labour" in topic_lower:
        values = [-0.4, 0.3, 0.2]
    elif "other" in topic_lower:
        values = [0.2, 0.4, 0.3]
    elif "policy" in topic_lower:
        values = [0.1, 0.0, -0.2]
    elif "trade" in topic_lower:
        values = [-0.6, -0.9, -0.5]
    elif "climate" in topic_lower:
        values = [0.3, 0.2, 0.4]
    else:
        values = [0.2, 0.3, 0.4]

    abs_values = [abs(v) for v in values]
    return labels, values, abs_values

# --- PDF CHART EXPORT ---
def generate_individual_pdfs(file_paths, output_dir):
    for path in file_paths:
        topic_name = os.path.splitext(os.path.basename(path))[0].replace("_", " ")
        output_pdf = os.path.join(output_dir, f"{topic_name}_charts.pdf")

        with open(path, "r") as file:
            text = file.read()

        labels, values, abs_values = interpret_generic_file(text, topic_name)

        with PdfPages(output_pdf) as pdf:
            # Bar Chart
            plt.figure(figsize=(10, 6))
            bars = plt.bar(labels, values)
            for bar, value in zip(bars, values):
                bar.set_color('green' if value > 0 else 'red' if value < 0 else 'gray')
                y_offset = -0.1 if value < 0 else 0.1
                plt.text(bar.get_x() + bar.get_width() / 2, value + y_offset,
                         f"{value}", ha='center', va='bottom' if value < 0 else 'top')
            plt.title(f"{topic_name} Impact Interpretation (Bar Chart)")
            plt.ylabel("Impact Score")
            plt.axhline(0, color='black')
            plt.grid(axis='y', linestyle='--', alpha=0.6)
            plt.tight_layout()
            pdf.savefig()
            plt.close()

            # Pie Chart
            plt.figure(figsize=(7, 7))
            pie_labels = [f"{label}: {abs(val)}" for label, val in zip(labels, values)]
            colors = ['blue', 'gray', 'orange']
            plt.pie(abs_values, labels=pie_labels, autopct='%1.1f%%', startangle=140, colors=colors[:len(labels)])
            plt.title(f"{topic_name} Share of Impact (Pie Chart)")
            plt.tight_layout()
            pdf.savefig()
            plt.close()

            # Line Chart
            years = list(range(2020, 2020 + 4 * len(values), 4))
            plt.figure(figsize=(10, 6))
            plt.plot(years, values, marker='o', linestyle='-', color='black')
            for x, y, label in zip(years, values, labels):
                plt.text(x, y + 0.05, f"{label}\n{y}", ha='center', va='bottom', fontsize=9)
            plt.title(f"{topic_name} Timeline of Impact (Line Chart)")
            plt.xlabel("Year")
            plt.ylabel("Impact Score")
            plt.grid(True)
            plt.tight_layout()
            pdf.savefig()
            plt.close()

# --- RUN ---
if __name__ == "__main__":
    input_dir = "./out"
    file_paths = [os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.endswith(".txt")]
    generate_individual_pdfs(file_paths, input_dir)
    print("✅ All chart PDFs generated in ./out/")
