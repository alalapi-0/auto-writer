"""去重逻辑自检脚本，用于快速验证强约束与近似约束是否生效。"""  # 模块中文说明
from __future__ import annotations  # 引入未来注解语法保证类型提示兼容
from sqlalchemy.orm import Session  # 导入 SQLAlchemy 会话类型
from app.db.migrate import SessionLocal  # 导入数据库会话工厂
from app.generator.persistence import insert_article_tx  # 导入事务写入函数


def get_db() -> Session:  # 定义会话获取函数
    """创建数据库会话实例，供脚本测试使用。"""  # 函数中文文档
    return SessionLocal()  # 返回新的数据库会话


def main() -> None:  # 定义脚本主函数
    """执行三种场景的去重验证并输出结果。"""  # 函数中文文档
    db = get_db()  # 创建数据库会话
    try:
        print("== 场景 A: 首次入库，预期成功 ==")  # 输出场景说明
        try:
            result = insert_article_tx(  # 调用写入逻辑
                session=db,  # 传入会话
                title="定义：边缘性人格的镜像撕裂（示例）",  # 指定标题
                body="这里是一段相同正文A ...",  # 指定正文
                role="Joker",  # 指定角色
                work="The Dark Knight",  # 指定作品
                keyword="边缘性人格",  # 指定关键词
                lang="zh",  # 指定语言
                run_id="doctor",  # 指定运行 ID
            )
            print("OK", result)  # 打印成功结果
        except Exception as exc:  # noqa: BLE001  # 捕获异常
            print("ERR", exc)  # 打印错误

        print("== 场景 B: 正文签名重复，预期失败 ==")  # 输出场景说明
        try:
            result = insert_article_tx(  # 再次调用写入逻辑
                session=db,  # 传入会话
                title="完全不同的标题也不行",  # 指定新标题
                body="这里是一段相同正文A ...",  # 与场景 A 相同正文
                role="Joker",  # 指定角色
                work="The Dark Knight",  # 指定作品
                keyword="边缘性人格",  # 指定关键词
                lang="zh",  # 指定语言
                run_id="doctor",  # 指定运行 ID
            )
            print("OK", result)  # 打印结果
        except Exception as exc:  # noqa: BLE001  # 捕获异常
            print("ERR", exc)  # 打印错误

        print("== 场景 C: 组合当日重复，预期失败 ==")  # 输出场景说明
        try:
            result = insert_article_tx(  # 再次写入
                session=db,  # 传入会话
                title="同组合同日再来一次",  # 指定标题
                body="换个正文，但组合一样",  # 指定不同正文
                role="Joker",  # 指定角色
                work="The Dark Knight",  # 指定作品
                keyword="边缘性人格",  # 指定关键词
                lang="zh",  # 指定语言
                run_id="doctor",  # 指定运行 ID
            )
            print("OK", result)  # 打印结果
        except Exception as exc:  # noqa: BLE001  # 捕获异常
            print("ERR", exc)  # 打印错误
    finally:
        db.close()  # 关闭数据库会话


if __name__ == "__main__":  # 判断是否直接执行脚本
    main()  # 运行主函数
