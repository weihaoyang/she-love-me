"""Deterministic SVG network map for the dashboard.

A small force-directed layout (repulsion + spring + gravity) keeps the output
self-contained: no JS, no external chart library, reproducible for the same data.
"""

import math
import random


def select_nodes(graph, limit=60):
    persons = [p for p in graph["persons"] if p.get("kind") == "person"]
    labelled = [p for p in persons if (p.get("label") or {}).get("tier")]
    chosen = {p["username"]: p for p in persons[:limit]}
    for person in labelled:
        chosen.setdefault(person["username"], person)
    return list(chosen.values())


def force_layout(nodes, edges, width=900, height=620, iterations=180, seed=7):
    random.seed(seed)
    count = len(nodes)
    if not count:
        return {}
    positions = {}
    for index, node in enumerate(nodes):
        angle = 2 * math.pi * index / count
        radius = min(width, height) * 0.32
        positions[node["username"]] = [
            width / 2 + radius * math.cos(angle) + random.uniform(-10, 10),
            height / 2 + radius * math.sin(angle) + random.uniform(-10, 10),
        ]
    adjacency = {node["username"]: [] for node in nodes}
    for edge in edges:
        if edge["a"] in adjacency and edge["b"] in adjacency:
            adjacency[edge["a"]].append(edge["b"])
            adjacency[edge["b"]].append(edge["a"])
    area = width * height
    k = math.sqrt(area / count)

    for _ in range(iterations):
        displacement = {name: [0.0, 0.0] for name in positions}
        names = list(positions)
        for i in range(count):
            a = names[i]
            ax, ay = positions[a]
            for j in range(i + 1, count):
                b = names[j]
                bx, by = positions[b]
                dx, dy = ax - bx, ay - by
                distance = math.hypot(dx, dy) or 0.01
                force = k * k / distance
                ux, uy = dx / distance, dy / distance
                displacement[a][0] += ux * force
                displacement[a][1] += uy * force
                displacement[b][0] -= ux * force
                displacement[b][1] -= uy * force
        for name, neighbours in adjacency.items():
            ax, ay = positions[name]
            for neighbour in neighbours:
                bx, by = positions[neighbour]
                dx, dy = ax - bx, ay - by
                distance = math.hypot(dx, dy) or 0.01
                force = distance * distance / k
                ux, uy = dx / distance, dy / distance
                displacement[name][0] -= ux * force
                displacement[name][1] -= uy * force
        for name in positions:
            dx, dy = displacement[name]
            length = math.hypot(dx, dy) or 0.01
            limit = min(length, 22)
            positions[name][0] += dx / length * limit
            positions[name][1] += dy / length * limit
            positions[name][0] = min(width - 30, max(30, positions[name][0]))
            positions[name][1] = min(height - 30, max(24, positions[name][1]))
    return positions


def _radius(person):
    return 3.2 + min(9.0, math.log10(max(person.get("total", 1), 1)) * 1.8)


def _color(person):
    days = person.get("days_since", 999)
    if days <= 30:
        return "#3f6f6a"
    if days <= 120:
        return "#a8703f"
    return "#b9b0a5"


def render_svg(graph, limit=60, width=900, height=620):
    nodes = select_nodes(graph, limit=limit)
    names = {node["username"] for node in nodes}
    edges = [edge for edge in graph.get("edges", [])
             if edge["a"] in names and edge["b"] in names]
    positions = force_layout(nodes, edges, width=width, height=height)
    if not positions:
        return ""

    lines = []
    for edge in edges:
        x1, y1 = positions[edge["a"]]
        x2, y2 = positions[edge["b"]]
        opacity = 0.10 + min(0.25, edge.get("weight", 1) * 0.05)
        lines.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                     f'stroke="#8fa8a3" stroke-width="0.8" opacity="{opacity:.2f}"/>')

    circles = []
    labels = []
    top = sorted(nodes, key=lambda p: -p["strength"])
    label_names = {p["username"] for p in top[:18]}
    label_names.update(p["username"] for p in nodes if (p.get("label") or {}).get("tier"))
    for person in nodes:
        x, y = positions[person["username"]]
        radius = _radius(person)
        circles.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" '
                       f'fill="{_color(person)}" fill-opacity="0.85" stroke="#fff" stroke-width="1"/>')
        if person["username"] in label_names:
            anchor = "start" if x < width * 0.55 else "end"
            dx = radius + 4 if anchor == "start" else -(radius + 4)
            labels.append(f'<text x="{x + dx:.1f}" y="{y + 3:.1f}" text-anchor="{anchor}" '
                          f'class="glabel">{person["name"][:10]}</text>')

    legend = (
        '<g transform="translate(14,14)">'
        '<circle cx="6" cy="6" r="4" fill="#3f6f6a" fill-opacity="0.85"/>'
        '<text x="16" y="10" class="glegend">30 天内</text>'
        '<circle cx="86" cy="6" r="4" fill="#a8703f" fill-opacity="0.85"/>'
        '<text x="96" y="10" class="glegend">30–120 天</text>'
        '<circle cx="186" cy="6" r="4" fill="#b9b0a5" fill-opacity="0.85"/>'
        '<text x="196" y="10" class="glegend">120 天以上</text>'
        '</g>'
    )
    return (f'<svg viewBox="0 0 {width} {height}" class="netmap">'
            + "".join(lines) + "".join(circles) + "".join(labels) + legend + "</svg>")
