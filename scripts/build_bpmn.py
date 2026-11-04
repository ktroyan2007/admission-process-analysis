"""Строит BPMN-схемы процесса «как есть» и «как должно быть».

Результат: bpmn/as_is.bpmn, bpmn/to_be.bpmn (BPMN 2.0, открываются в Camunda Modeler,
на demo.bpmn.io или в draw.io) и PNG-превью для README.  Запуск: python scripts/build_bpmn.py"""
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, Circle, Rectangle

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "bpmn"
OUT.mkdir(exist_ok=True)

LANES = ["Абитуриент", "Сотрудник комиссии", "Информационная система"]
X0, Y0 = 40, 40          # левый верхний угол пула
LABEL_W = 34             # полоса с названием пула
LANE_LABEL_W = 30        # полоса с названием дорожки
LANE_H = 150
COL_W = 165
FIRST_X = X0 + LABEL_W + LANE_LABEL_W + 40
SIZE = {"start": (36, 36), "end": (36, 36), "task": (124, 72), "xor": (50, 50)}
PAIN = "#c0392b"


class Node:
    def __init__(self, id, kind, lane, col, name, pain=None):
        self.id, self.kind, self.lane, self.col, self.name, self.pain = id, kind, lane, col, name, pain
        self.w, self.h = SIZE[kind]
        self.cx = FIRST_X + col * COL_W + SIZE["task"][0] / 2
        self.cy = Y0 + lane * LANE_H + LANE_H / 2
        self.x, self.y = self.cx - self.w / 2, self.cy - self.h / 2

    def side(self, s):
        return {"l": (self.x, self.cy), "r": (self.x + self.w, self.cy),
                "t": (self.cx, self.y), "b": (self.cx, self.y + self.h)}[s]


def route(a, b, back_same_lane=False):
    if back_same_lane:                                   # возврат назад внутри дорожки — поверху
        top = Y0 + a.lane * LANE_H + 14
        return [a.side("t"), (a.cx, top), (b.cx, top), b.side("t")]
    if a.lane == b.lane:
        return [a.side("r"), b.side("l")]
    down = b.lane > a.lane
    if a.col == b.col:
        return [a.side("b" if down else "t"), b.side("t" if down else "b")]
    s = a.side("r" if b.col > a.col else "l")
    return [s, (b.cx, s[1]), b.side("t" if down else "b")]


def build(name, title, nodes, flows):
    nd = {n.id: n for n in nodes}
    ncols = max(n.col for n in nodes) + 1
    pool_w = (FIRST_X - X0) + ncols * COL_W + 10
    pool_h = LANE_H * len(LANES)
    edges = []
    for i, f in enumerate(flows, 1):
        src, dst = nd[f[0]], nd[f[1]]
        label = f[2] if len(f) > 2 else ""
        back = len(f) > 3 and f[3] == "back"
        edges.append((f"Flow_{i}", src, dst, label, route(src, dst, back)))

    # ---------- BPMN 2.0 XML ----------
    tag = {"start": "startEvent", "end": "endEvent", "task": "task", "xor": "exclusiveGateway"}
    proc = [f'<bpmn:process id="Process_{name}" isExecutable="false">', '<bpmn:laneSet id="LaneSet_1">']
    for li, ln in enumerate(LANES):
        proc.append(f'<bpmn:lane id="Lane_{li}" name="{escape(ln)}">')
        proc += [f"<bpmn:flowNodeRef>{n.id}</bpmn:flowNodeRef>" for n in nodes if n.lane == li]
        proc.append("</bpmn:lane>")
    proc.append("</bpmn:laneSet>")
    for n in nodes:
        inc = "".join(f"<bpmn:incoming>{e[0]}</bpmn:incoming>" for e in edges if e[2] is n)
        out = "".join(f"<bpmn:outgoing>{e[0]}</bpmn:outgoing>" for e in edges if e[1] is n)
        proc.append(f'<bpmn:{tag[n.kind]} id="{n.id}" name="{escape(n.name)}">{inc}{out}</bpmn:{tag[n.kind]}>')
    for fid, s, d, label, _ in edges:
        nm = f' name="{escape(label)}"' if label else ""
        proc.append(f'<bpmn:sequenceFlow id="{fid}"{nm} sourceRef="{s.id}" targetRef="{d.id}" />')
    proc.append("</bpmn:process>")

    di = [f'<bpmndi:BPMNDiagram id="Diagram_{name}"><bpmndi:BPMNPlane id="Plane_{name}" bpmnElement="Collab_{name}">',
          f'<bpmndi:BPMNShape id="Pool_{name}_di" bpmnElement="Pool_{name}" isHorizontal="true">'
          f'<dc:Bounds x="{X0}" y="{Y0}" width="{pool_w}" height="{pool_h}" /></bpmndi:BPMNShape>']
    for li in range(len(LANES)):
        di.append(f'<bpmndi:BPMNShape id="Lane_{li}_di" bpmnElement="Lane_{li}" isHorizontal="true">'
                  f'<dc:Bounds x="{X0 + LABEL_W}" y="{Y0 + li * LANE_H}" width="{pool_w - LABEL_W}" height="{LANE_H}" />'
                  f'</bpmndi:BPMNShape>')
    for n in nodes:
        color = f' bioc:stroke="{PAIN}" bioc:fill="#fdecea" color:border-color="{PAIN}" color:background-color="#fdecea"' if n.pain else ""
        lab = ""
        if n.kind in ("xor", "start", "end"):
            ly = n.y - 34 if n.kind == "end" else n.y + n.h + 6
            lab = (f'<bpmndi:BPMNLabel><dc:Bounds x="{n.cx - 55}" y="{ly:.0f}" width="110" height="28" />'
                   f'</bpmndi:BPMNLabel>')
        di.append(f'<bpmndi:BPMNShape id="{n.id}_di" bpmnElement="{n.id}"{color}>'
                  f'<dc:Bounds x="{n.x:.0f}" y="{n.y:.0f}" width="{n.w}" height="{n.h}" />{lab}</bpmndi:BPMNShape>')
    for fid, s, d, label, pts in edges:
        wps = "".join(f'<di:waypoint x="{x:.0f}" y="{y:.0f}" />' for x, y in pts)
        lab = ""
        if label:
            (x1, y1), (x2, y2) = pts[0], pts[1]
            lab = (f'<bpmndi:BPMNLabel><dc:Bounds x="{(x1 + x2) / 2 + 4:.0f}" y="{(y1 + y2) / 2 - 18:.0f}" '
                   f'width="40" height="14" /></bpmndi:BPMNLabel>')
        di.append(f'<bpmndi:BPMNEdge id="{fid}_di" bpmnElement="{fid}">{wps}{lab}</bpmndi:BPMNEdge>')
    di.append("</bpmndi:BPMNPlane></bpmndi:BPMNDiagram>")

    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
           'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
           'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" '
           'xmlns:bioc="http://bpmn.io/schema/bpmn/biocolor/1.0" '
           'xmlns:color="http://www.omg.org/spec/BPMN/non-normative/color/1.0" '
           f'id="Definitions_{name}" targetNamespace="http://bpmn.io/schema/bpmn">\n'
           f'<bpmn:collaboration id="Collab_{name}"><bpmn:participant id="Pool_{name}" '
           f'name="{escape(title)}" processRef="Process_{name}" /></bpmn:collaboration>\n'
           + "\n".join(proc) + "\n" + "\n".join(di) + "\n</bpmn:definitions>\n")
    (OUT / f"{name}.bpmn").write_text(xml, encoding="utf-8")

    # ---------- PNG-превью ----------
    W, H = X0 * 2 + pool_w, Y0 * 2 + pool_h + 30
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=150)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    ink, line = "#1f2430", "#55606e"
    ax.add_patch(Rectangle((X0, Y0), pool_w, pool_h, fill=False, lw=1.4, ec=ink))
    ax.add_patch(Rectangle((X0, Y0), LABEL_W, pool_h, fill=True, fc="#eef1f6", lw=1.4, ec=ink))
    ax.text(X0 + LABEL_W / 2, Y0 + pool_h / 2, title, rotation=90, ha="center", va="center", fontsize=9.5, fontweight="bold", color=ink)
    for li, ln in enumerate(LANES):
        y = Y0 + li * LANE_H
        ax.add_patch(Rectangle((X0 + LABEL_W, y), pool_w - LABEL_W, LANE_H, fill=False, lw=1, ec=ink))
        ax.add_patch(Rectangle((X0 + LABEL_W, y), LANE_LABEL_W, LANE_H, fill=True, fc="#f6f7f9", lw=1, ec=ink))
        ax.text(X0 + LABEL_W + LANE_LABEL_W / 2, y + LANE_H / 2, "\n".join(textwrap.wrap(ln, 14)), rotation=90,
                ha="center", va="center", fontsize=8.2, color=ink)
    for fid, s, d, label, pts in edges:
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color=line, lw=1.2, solid_joinstyle="miter", zorder=1)
        ax.annotate("", xy=pts[-1], xytext=pts[-2],
                    arrowprops=dict(arrowstyle="-|>", color=line, lw=1.2, mutation_scale=11, shrinkA=0, shrinkB=0), zorder=1)
        if label:
            (x1, y1), (x2, y2) = pts[0], pts[1]
            ax.text((x1 + x2) / 2 + 5, (y1 + y2) / 2 - 6, label, fontsize=8, color=ink, ha="left", va="bottom", style="italic")
    for n in nodes:
        ec = PAIN if n.pain else ink
        fc = "#fdecea" if n.pain else "white"
        if n.kind == "task":
            ax.add_patch(FancyBboxPatch((n.x, n.y), n.w, n.h, boxstyle="round,pad=0,rounding_size=10", fc=fc, ec=ec, lw=1.5, zorder=2))
            ax.text(n.cx, n.cy, "\n".join(textwrap.wrap(n.name, 20)), ha="center", va="center", fontsize=7.6, color=ink, zorder=3)
        elif n.kind == "xor":
            ax.add_patch(Polygon([(n.cx, n.y), (n.x + n.w, n.cy), (n.cx, n.y + n.h), (n.x, n.cy)], closed=True, fc="white", ec=ink, lw=1.5, zorder=2))
            ax.text(n.cx, n.cy, "×", ha="center", va="center", fontsize=16, color=ink, zorder=3)
            ax.text(n.cx, n.y + n.h + 6, "\n".join(textwrap.wrap(n.name, 18)), ha="center", va="top", fontsize=7.6, color=ink, zorder=3)
        else:
            ax.add_patch(Circle((n.cx, n.cy), n.w / 2, fc="white", ec=ink, lw=1.3 if n.kind == "start" else 3, zorder=2))
            if n.kind == "end":
                ax.text(n.cx, n.y - 6, "\n".join(textwrap.wrap(n.name, 16)), ha="center", va="bottom", fontsize=7.6, color=ink, zorder=3)
            else:
                ax.text(n.cx, n.y + n.h + 6, "\n".join(textwrap.wrap(n.name, 16)), ha="center", va="top", fontsize=7.6, color=ink, zorder=3)
        if n.pain:
            ax.add_patch(Circle((n.x + n.w - 2, n.y + 2), 10, fc=PAIN, ec="white", lw=1.2, zorder=4))
            ax.text(n.x + n.w - 2, n.y + 2.5, str(n.pain), ha="center", va="center", fontsize=8, color="white", fontweight="bold", zorder=5)
    if any(n.pain for n in nodes):
        ax.text(X0, Y0 + pool_h + 18, "Красным отмечены узкие места, номера соответствуют разделу «Узкие места» в README.",
                fontsize=8, color=PAIN, va="top")
    fig.savefig(OUT / f"{name}.png", dpi=150, facecolor="white")
    plt.close(fig)


AB, OP, SY = 0, 1, 2
as_is = [
    Node("Start_1", "start", AB, 0, "Решил поступать"),
    Node("Task_submit", "task", AB, 1, "Подать заявление и документы (Госуслуги, ЛК или лично)"),
    Node("Task_register", "task", SY, 2, "Зарегистрировать заявление"),
    Node("Task_check", "task", OP, 3, "Проверить вручную документы, баллы ЕГЭ в ФИС и дубли", pain=1),
    Node("Gw_errors", "xor", OP, 4, "Есть ошибки?"),
    Node("Task_fix", "task", AB, 4, "Исправить данные по звонку или письму комиссии", pain=2),
    Node("Task_input", "task", OP, 5, "Перенести данные в базу вручную", pain=3),
    Node("Task_list", "task", SY, 6, "Включить в конкурсный список"),
    Node("End_1", "end", AB, 7, "Заявление принято"),
]
as_is_flows = [
    ("Start_1", "Task_submit"), ("Task_submit", "Task_register"), ("Task_register", "Task_check"),
    ("Task_check", "Gw_errors"), ("Gw_errors", "Task_fix", "да"), ("Task_fix", "Task_check"),
    ("Gw_errors", "Task_input", "нет"), ("Task_input", "Task_list"), ("Task_list", "End_1"),
]
build("as_is", "Приём заявлений: как есть", as_is, as_is_flows)

to_be = [
    Node("Start_1", "start", AB, 0, "Решил поступать"),
    Node("Task_submit", "task", AB, 1, "Подать заявление и документы (Госуслуги, ЛК или лично)"),
    Node("Task_autocheck", "task", SY, 2, "Автопроверка: формат СНИЛС и паспорта, согласие, документ об образовании"),
    Node("Gw_errors", "xor", SY, 3, "Ошибки найдены?"),
    Node("Task_fix", "task", AB, 3, "Исправить ошибку по подсказке на экране"),
    Node("Task_fis", "task", SY, 4, "Сверить баллы с ФИС и проверить дубли автоматически"),
    Node("Gw_manual", "xor", SY, 5, "Нужна ручная проверка?"),
    Node("Task_manual", "task", OP, 5, "Проверить спорное заявление"),
    Node("Task_list", "task", SY, 6, "Включить в конкурсный список и уведомить абитуриента"),
    Node("End_1", "end", AB, 7, "Заявление принято"),
]
to_be_flows = [
    ("Start_1", "Task_submit"), ("Task_submit", "Task_autocheck"), ("Task_autocheck", "Gw_errors"),
    ("Gw_errors", "Task_fix", "да"), ("Task_fix", "Task_submit", "", "back"),
    ("Gw_errors", "Task_fis", "нет"), ("Task_fis", "Gw_manual"),
    ("Gw_manual", "Task_manual", "да"), ("Task_manual", "Task_list"),
    ("Gw_manual", "Task_list", "нет"), ("Task_list", "End_1"),
]
build("to_be", "Приём заявлений: как должно быть", to_be, to_be_flows)
print("ok")
