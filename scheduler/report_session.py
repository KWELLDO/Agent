# ===== 引入区 =====
from langchain_core.messages import HumanMessage

from scheduler.models import ReportEntry
from scheduler.cron_agent import build_cron_agent

from logger import get_logger


# ===== 定义区 =====
def run_report_session(store) -> None:
    print("\n===== Cron 报告会话 =====")
    print("输入 exit_cron 返回主会话")
    print("输入编号查看详情，输入后可在详情中回复\n")

    while True:
        try:
            unread = store.get_unread_reports()
            recent = store.get_all_reports(limit=10)

            if not recent:
                print("[暂无定时任务报告]")
            else:
                print(f"--- 最近报告 (未读: {len(unread)}) ---")
                for i, r in enumerate(reversed(recent), 1):
                    marker = " [新]" if not r.read else "    "
                    print(f"  {i}{marker} [{r.triggered_at[:19]}] Job#{r.job_id[:8]}: {r.summary(60)}")

            inp = input("[Cron] ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not inp:
            continue
        if inp.lower() == "exit_cron":
            break

        if inp.isdigit():
            idx = int(inp)
            recent_list = list(reversed(store.get_all_reports(limit=10)))
            if idx < 1 or idx > len(recent_list):
                print(f"无效编号，范围 1-{len(recent_list)}")
                continue
            report = recent_list[idx - 1]
            _show_report(store, report)

    print("已退出 Cron 报告会话\n")


def _show_report(store, report: ReportEntry) -> None:
    store.mark_report_read(report.report_id)

    print(f"\n===== 报告详情 =====")
    print(f"任务 ID:   {report.job_id}")
    print(f"触发时间:  {report.triggered_at}")
    print(f"任务指令:  {report.task_prompt}")
    print(f"--- 执行结果 ---")
    print(report.output[:2000])
    if len(report.output) > 2000:
        print("...(结果过长已截断)")
    print(f"\n--- 对话 ({len(report.conversation)} 条) ---")
    for msg in report.conversation:
        role_tag = "你" if msg.get("role") == "user" else "Agent"
        print(f"  [{role_tag}] {msg.get('content', '')[:200]}")
    print()

    while True:
        reply = input("[Cron 回复] 输入回复内容，或按回车跳过: ").strip()
        if not reply:
            break
        msg = report.to_conversation_msg("user", reply)
        store.append_report_conversation(report.report_id, msg)

        agent = build_cron_agent()
        if agent is None:
            print("[错误] 无法构建 Cron Agent")
            reply_output = "[Cron Agent 构建失败]"
        else:
            try:
                result = agent.invoke({"messages": [HumanMessage(content=reply)]})
                if isinstance(result, dict) and "messages" in result:
                    reply_output = result["messages"][-1].content or ""
                else:
                    reply_output = str(result)
            except Exception:
                logger.exception("Cron 回复失败")
                reply_output = "[Cron Agent 回复异常]"

        reply_msg = report.to_conversation_msg("agent", reply_output)
        store.append_report_conversation(report.report_id, reply_msg)
        print(f"[Agent] {reply_output[:600]}")
        print()


# ===== 执行区 =====
logger = get_logger("report_session")
