from flask import Flask, render_template, request
import os
import re
from pdf2image import convert_from_path

app = Flask(__name__)

CHART_DIR = os.path.join("static", "charts")




# Load single-category stories from 9 text files
def load_stories():
    base_path = "data"
    story_files = [
        "story_Construction.txt", "story_Economic Recovery.txt", "story_Energy.txt",
        "story_Finance.txt", "story_Industry.txt", "story_Labour.txt",
        "story_Other.txt", "story_Policy.txt", "story_Trade.txt", "story_Climate.txt"
    ]
    stories = {}
    for file in story_files:
        path = os.path.join(base_path, file)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                stories[file.replace("story_", "").replace(".txt", "").strip()] = f.read()
    return stories

# Convert chart PDFs to PNGs for inline display
def convert_charts():
    os.makedirs(CHART_DIR, exist_ok=True)
    for file in os.listdir(CHART_DIR):
        if file.endswith("_charts.pdf"):
            pdf_path = os.path.join(CHART_DIR, file)
            base_name = file.replace(".pdf", "")
            try:
                images = convert_from_path(pdf_path, dpi=150)
                for i, image in enumerate(images):
                    image_path = os.path.join(CHART_DIR, f"{base_name}_page_{i+1}.png")
                    if not os.path.exists(image_path):
                        image.save(image_path, "PNG")
            except Exception as e:
                print(f"Error converting {file}: {e}")

# Robust story splitter
def split_story(story):
    try:
        past = re.split(r'(?i)paragraph\s*2', story)[0]
        middle = re.split(r'(?i)paragraph\s*2', story)[1]
        present = re.split(r'(?i)paragraph\s*3', middle)[0]
        future = re.split(r'(?i)paragraph\s*3', story)[1].split("**References")[0]
        return past.strip(), present.strip(), future.strip()
    except Exception:
        return "Could not split story", "Could not split story", "Could not split story"
#load graph (visulazation)
@app.route("/view-chart", methods=["GET", "POST"])
def view_chart():
    categories = [
        "Climate", "Construction", "Economic Recovery", "Energy",
        "Finance", "Industry", "Labour", "Other", "Policy", "Trade"
    ]

    chart_type_map = {
        "Bar Chart": "page_1",
        "Pie Chart": "page_2",
        "Line Chart": "page_3"
    }

    chart_files = []
    selected_topic = None
    selected_chart_type = None

    if request.method == "POST":
        selected_topic = request.form.get("topic")
        selected_chart_type = request.form.get("chart")

        if selected_topic:
            if selected_chart_type == "All":
                for label, page_suffix in chart_type_map.items():
                    filename = f"story_{selected_topic}_charts_{page_suffix}.png"
                    file_path = os.path.join(CHART_DIR, filename)
                    if os.path.exists(file_path):
                        chart_files.append((label, filename))
            else:
                page_suffix = chart_type_map.get(selected_chart_type)
                if page_suffix:
                    filename = f"story_{selected_topic}_charts_{page_suffix}.png"
                    file_path = os.path.join(CHART_DIR, filename)
                    if os.path.exists(file_path):
                        chart_files.append((selected_chart_type, filename))

    return render_template("visulazation.html",
                           topics=categories,
                           chart_types=["Bar Chart", "Pie Chart", "Line Chart", "All"],
                           selected=selected_topic,
                           selected_chart_type=selected_chart_type,
                           chart_files=chart_files)


# Load combined story for selected categories (no args, read from request.form)
def load_combined_story():
    base_dir = "./data/compare-20250706T225351Z-1-001/compare"
    cat1 = request.form.get("category1")
    cat2 = request.form.get("category2")

    if not cat1 or not cat2 or cat1 == cat2:
        return None

    filenames = [
        f"{cat1}_vs_{cat2}.txt",
        f"{cat2}_vs_{cat1}.txt"
    ]
    for fname in filenames:
        fpath = os.path.join(base_dir, fname)
        if os.path.exists(fpath):
            with open(fpath, encoding="utf-8") as f:
                content = f.read()
                # Remove everything after **References**
                content = re.split(r"\*\*References", content, flags=re.IGNORECASE)[0].strip()
                return content
    return None


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/generating-stories")
def generating_stories():
    return render_template("generating_story.html")

@app.route("/complete-stories")
def complete_stories():
    convert_charts()
    stories = load_stories()
    all_categories = sorted(stories.keys())

    selected_categories = request.args.getlist("category") or all_categories

    filtered_stories = {cat: story for cat, story in stories.items() if cat in selected_categories}

    structured_stories = {}
    for cat, story in filtered_stories.items():
        past, present, future = split_story(story)
        structured_stories[cat] = {
            "past": past,
            "present": present,
            "future": future
        }

    return render_template("complete_stories.html",
                           categories=all_categories,
                           selected_categories=selected_categories,
                           filtered_stories=structured_stories)

@app.route("/compare-stories", methods=["GET", "POST"])
def compare_stories():
    categories = [
        "Climate", "Construction", "Economic Recovery", "Energy",
        "Finance", "Industry", "Labour", "Other", "Policy", "Trade"
    ]

    selected_1 = request.form.get("category1")
    selected_2 = request.form.get("category2")
    story_text = load_combined_story()

    return render_template("combine_stories.html",
                           categories=categories,
                           selected_1=selected_1,
                           selected_2=selected_2,
                           story=story_text)

if __name__ == "__main__":
    app.run(debug=True)
