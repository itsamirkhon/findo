"""Service for generating financial charts using matplotlib."""
import uuid
from typing import List, Dict, Any

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt

def generate_custom_chart(title: str, chart_type: str, labels: List[str], datasets: List[Dict[str, Any]]) -> str:
    """
    Generates a highly customizable chart based on explicit parameters.
    
    chart_type: 'bar', 'line', 'pie'
    labels: X-axis labels or slice labels
    datasets: [
        {"label": "Income", "data": [10, 20, 30], "color": "#1dd1a1"},
        {"label": "Expense", "data": [15, 10, 25], "color": "#ff6b6b"}
    ]
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor('#2C2F33')
    ax.set_facecolor('#2C2F33')
    
    ax.set_title(title, color="white", fontsize=16, weight="bold")
    
    if chart_type == "pie":
        # For pie charts, we typically use only the first dataset
        if datasets and len(datasets[0].get("data", [])) > 0:
            ds = datasets[0]
            sizes = ds.get("data", [])
            # Fill with default colors if none provided
            colors = ds.get("colors") or ["#ff6b6b", "#feca57", "#1dd1a1", "#0abde3", "#c8d6e5"][:len(sizes)]
            
            wedges, texts, autotexts = ax.pie(
                sizes, labels=labels[:len(sizes)], colors=colors, autopct='%1.1f%%',
                startangle=90, textprops=dict(color="w", weight="bold")
            )
            for t in texts:
                t.set_color("white")
        else:
            ax.text(0.5, 0.5, 'Нет данных', horizontalalignment='center', verticalalignment='center', fontsize=20, color='white')
            ax.axis('off')
            
    elif chart_type == "line":
        for ds in datasets:
            color = ds.get("color", "#1dd1a1")
            ax.plot(labels, ds.get("data", []), marker='o', label=ds.get("label", ""), color=color, linewidth=2)
            
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, color="white")
        ax.tick_params(colors="white")
        ax.grid(True, linestyle='--', alpha=0.3, color='white')
        if datasets and any(ds.get("label") for ds in datasets):
            ax.legend(facecolor='#2C2F33', edgecolor='white', labelcolor='white')
            
    else:  # "bar" and defaults to bar
        x = range(len(labels))
        num_datasets = len(datasets)
        
        # Calculate bar width based on number of datasets
        width = 0.8 / max(1, num_datasets)
        
        for i, ds in enumerate(datasets):
            color = ds.get("color", "#ff6b6b")
            offset = (i - num_datasets / 2 + 0.5) * width
            ax.bar([pos + offset for pos in x], ds.get("data", []), width, label=ds.get("label", ""), color=color)
            
        ax.set_xticks(x)
        ax.set_xticklabels(labels, color="white")
        ax.tick_params(colors="white")
        ax.grid(True, linestyle='--', alpha=0.3, color='white', axis='y')
        if datasets and any(ds.get("label") for ds in datasets):
            ax.legend(facecolor='#2C2F33', edgecolor='white', labelcolor='white')
            
    filename = f"/tmp/chart_{chart_type}_{uuid.uuid4().hex[:8]}.png"
    plt.tight_layout()
    plt.savefig(filename, facecolor=fig.get_facecolor(), transparent=False)
    plt.close(fig)
    return filename
