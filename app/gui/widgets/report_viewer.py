# -*- coding: utf-8 -*-  # 指定 UTF-8 编码
"""报表面板，展示表格与图表。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

from typing import Dict, List  # 类型注解

from PySide6.QtCharts import (  # 图表控件
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QLineSeries,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import QPointF, Qt  # 点坐标与对齐常量
from PySide6.QtGui import QPainter  # 开启抗锯齿
from PySide6.QtWidgets import (  # Qt 控件
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ReportViewer(QWidget):  # 报表组件
    """显示导出报表的关键指标。"""  # 类说明

    def __init__(self, parent: QWidget | None = None) -> None:  # 构造函数
        super().__init__(parent)  # 初始化父类
        self.controller = None  # 保存控制器引用
        self._build_ui()  # 构建界面

    def _build_ui(self) -> None:  # 构建界面
        layout = QVBoxLayout(self)  # 主垂直布局
        self.info_label = QLabel("尚未加载报表", self)  # 顶部说明
        layout.addWidget(self.info_label)  # 添加标签
        self.table = QTableWidget(self)  # 数据表格
        self.table.setColumnCount(2)  # 设置两列
        self.table.setHorizontalHeaderLabels(["指标", "值"])  # 表头
        self.table.horizontalHeader().setStretchLastSection(True)  # 最后一列拉伸
        self.table.verticalHeader().setVisible(False)  # 隐藏行号
        layout.addWidget(self.table)  # 添加表格
        chart_row = QHBoxLayout()  # 第一排图表
        self.line_view = QChartView(self)  # 折线图视图
        self.line_view.setRenderHint(QPainter.Antialiasing)  # 开启抗锯齿
        chart_row.addWidget(self.line_view)  # 添加折线图
        self.pie_view = QChartView(self)  # 饼图视图
        self.pie_view.setRenderHint(QPainter.Antialiasing)  # 抗锯齿
        chart_row.addWidget(self.pie_view)  # 添加饼图
        layout.addLayout(chart_row)  # 将第一排加入布局
        self.bar_view = QChartView(self)  # 柱状图视图
        self.bar_view.setRenderHint(QPainter.Antialiasing)  # 抗锯齿
        layout.addWidget(self.bar_view)  # 添加柱状图

    def set_controller(self, controller) -> None:  # 注入控制器
        self.controller = controller  # 保存引用

    def update_report(self, data: Dict) -> None:  # 更新报表显示
        window = data.get("window", {})  # 获取时间窗口
        self.info_label.setText(f"统计窗口: {window.get('start', '-') } 至 {window.get('end', '-')}")  # 更新说明
        self._update_table(data)  # 更新表格
        metrics = data.get("metrics", {})  # 提取指标
        self._update_line_chart(metrics.get("article_counts", {}))  # 更新折线图
        self._update_pie_chart(metrics.get("platform", []))  # 更新饼图
        top_entities = metrics.get("top_entities", {})  # 获取热门实体
        self._update_bar_chart(top_entities.get("keywords", []))  # 更新柱状图

    def _update_table(self, data: Dict) -> None:  # 更新表格
        metrics = data.get("metrics", {})  # 提取指标
        rows = [  # 构造摘要
            ("生成时间", data.get("generated_at", "-")),
            ("文章总数", sum(metrics.get("article_counts", {}).values()) if metrics.get("article_counts") else 0),
            ("启用平台数", len(metrics.get("platform", []))),
            ("主题库存提示", metrics.get("dedup_hits", {})),
        ]
        self.table.setRowCount(len(rows))  # 设置行数
        for row, (name, value) in enumerate(rows):  # 遍历
            self.table.setItem(row, 0, QTableWidgetItem(str(name)))  # 写入指标
            self.table.setItem(row, 1, QTableWidgetItem(str(value)))  # 写入值

    def _update_line_chart(self, counts: Dict[str, int]) -> None:  # 更新折线图
        chart = QChart()  # 创建图表
        chart.setTitle("近 7 日生成量")  # 设置标题
        series = QLineSeries()  # 创建折线序列
        if not counts:  # 若无数据
            series.append(QPointF(0.0, 0.0))  # 添加占位点
        for idx, day in enumerate(sorted(counts.keys())):  # 按日期排序
            series.append(QPointF(float(idx), counts[day]))  # 使用索引作为 X 轴
        chart.addSeries(series)  # 添加序列
        axis_x = QValueAxis()  # X 轴使用数值轴
        axis_x.setTickCount(max(len(counts), 1))  # 设置刻度
        axis_x.setLabelFormat("%d")  # 设置标签格式
        axis_x.setTitleText("天数序号")  # 标题
        axis_y = QValueAxis()  # Y 轴
        axis_y.setLabelFormat("%d")  # 设置标签格式
        axis_y.setTitleText("篇数")  # 标题
        chart.addAxis(axis_x, Qt.AlignBottom)  # 添加 X 轴
        chart.addAxis(axis_y, Qt.AlignLeft)  # 添加 Y 轴
        series.attachAxis(axis_x)  # 序列附加 X 轴
        series.attachAxis(axis_y)  # 序列附加 Y 轴
        self.line_view.setChart(chart)  # 更新视图

    def _update_pie_chart(self, platforms: List[Dict]) -> None:  # 更新饼图
        chart = QChart()  # 创建图表
        chart.setTitle("平台成功率")  # 设置标题
        series = QPieSeries()  # 饼图序列
        total = 0  # 总数
        for item in platforms:  # 遍历平台数据
            success = item.get("success", 0)  # 成功数
            total += success  # 累加
            series.append(item.get("platform", "未知"), success)  # 添加分片
        if total == 0:  # 若无数据
            series.append("暂无数据", 1)  # 添加占位
        chart.addSeries(series)  # 添加序列
        self.pie_view.setChart(chart)  # 更新视图

    def _update_bar_chart(self, keywords: List[Dict]) -> None:  # 更新柱状图
        chart = QChart()  # 创建图表
        chart.setTitle("Top10 关键词")  # 标题
        bar_set = QBarSet("出现次数")  # 数据集
        categories = []  # 类别标签
        for item in keywords[:10]:  # 取前十
            categories.append(item.get("keyword", "未知"))  # 记录类别
            bar_set.append(float(item.get("count", 0)))  # 追加数据
        series = QBarSeries()  # 柱状序列
        series.append(bar_set)  # 添加数据集
        chart.addSeries(series)  # 添加序列
        axis_x = QBarCategoryAxis()  # X 轴分类
        axis_x.append(categories)  # 添加类别
        chart.addAxis(axis_x, Qt.AlignBottom)  # 附加 X 轴
        series.attachAxis(axis_x)  # 序列绑定 X 轴
        axis_y = QValueAxis()  # Y 轴
        axis_y.setTitleText("次数")  # 标题
        chart.addAxis(axis_y, Qt.AlignLeft)  # 附加 Y 轴
        series.attachAxis(axis_y)  # 序列绑定 Y 轴
        self.bar_view.setChart(chart)  # 更新视图
