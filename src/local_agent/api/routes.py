#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API路由定义
定义所有FastAPI接口路由
"""

from fastapi import APIRouter, Body
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Any

from ..config import get_config
from ..logger import get_logger
from local_agent.utils.http_client import http_post, http_put
from ..utils.timer_utils import clear_timeout
from ..core.global_cache import cache, set_agent_status, set_dmr_info, get_agent_status_by_key, get_dmr_upload_task_id, get_dmr_info, set_dmr_upload_task_id
from ..core.constants import HARDWARE_INFO_TASK_ID
from ..utils.timer_utils import set_timeout
from ..utils.time_utils import TimeUtils
from ..core.app_update import update_app

router = APIRouter()
logger = get_logger(__name__)
config = get_config()

class EKResultEvent(BaseModel):
    """EK结果汇报请求模型"""
    type: str
    status_code: str
    details: Dict[str, Any]

class EKResultRequest(BaseModel):
    """EK结果汇报请求模型"""
    tool: str
    timestamp: str
    session_id: str
    event: EKResultEvent

class DMRResultDetails(BaseModel):
    """EK结果汇报请求模型"""
    mode: str
    output_file: str
    output_data: Dict[str, Any]

class DMRResultEvent(BaseModel):
    """EK结果汇报请求模型"""
    type: str
    status_code: str
    details: DMRResultDetails

class DMRResultPayload(BaseModel):
    """EK结果汇报请求模型"""
    tool: str
    timestamp: str
    event: DMRResultEvent

class DMRResultRequest(BaseModel):
    """EK结果汇报请求模型"""
    Payload: DMRResultPayload

class CommonResponse(BaseModel):
    """通用响应模型"""
    code: int  # 0-成功, 1-失败
    msg: str


@router.post("/ek/start/result", response_model=CommonResponse)
async def ek_start_result(request: EKResultRequest):
    """
    EK启动结果汇报接口
    
    
    """
    try:
        
        logger.info(f"启动结果: {request}")

        event = request.event

        details = event.details

        # 启动结果上报
        case_res = http_post(url="/host/agent/testcase/report", data={
            "tc_id": details.get('tc_id', ''),
            # "state": 1,
            "state": 1 if event.status_code == '0' else 3,
            "result_msg": "{\"code\":\"200\",\"msg\":\"ok\"}",
            "log_url": "无",
        })

        if event.status_code == '1':
            return CommonResponse(
                code=0,
                msg="success"
            )

        # due_time = TimeUtils.add_minutes_to_current(details.get('estimated_duration', 0))

        # 上报测试用例预期结束时间
        res = http_put(url="/host/agent/testcase/due-time", data={
            "tc_id": details.get('tc_id', ''),
            "due_time": int(details.get('estimated_duration', 0))
        })

        logger.debug(f"启动结果上报响应: {res}")
        
        res_data = res.get('data', {})
        res_code = res_data.get('code', 0)
        if res_code != 200:
            logger.error(f"启动结果上报失败: {res}")

        set_agent_status(test=True)
        return CommonResponse(
            code=res_data.get('code'),
            msg=res_data.get('message')
        )

    except Exception as e:
        logger.error(f"处理启动结果汇报时发生错误: {str(e)}")
        return CommonResponse(
            code=1,
            msg=f"处理失败: {str(e)}"
        )


@router.post("/ek/test/result", response_model=CommonResponse)
async def report_tool_result(request: EKResultRequest):
    """
    EK结果汇报接口
    
    此接口等待EK调用，调用后将整理好的信息上报给服务端
    """
    try:
        
        logger.info(f"ek 结果详情: {request}")

        event = request.event

        details = event.details

        # 测试结果上报
        res = http_post(url="/host/agent/testcase/report", data={
            "tc_id": details.get('tc_id', ''),
            "state": 2 if event.status_code == '0' else 3,
            "result_msg": "{\"code\":\"200\",\"msg\":\"ok\"}",
            "log_url": "无",
        })

        logger.debug(f"测试结果上报响应: {res}")
        
        res_data = res.get('data', {})
        res_code = res_data.get('code', 0)
        if res_code != 200:
            logger.error(f"测试结果上报失败: {res}")

            return CommonResponse(
                code=res_data.get('code'),
                msg=res_data.get('message')
            )
        
        # 上报硬件信息
        dmr_res = upload_dmr()

        if dmr_res:
            # 记录测试状态
            set_agent_status(test=False)

        return CommonResponse(
            code=res_data.get('code'),
            msg=res_data.get('message')
        )

    except Exception as e:
        logger.error(f"处理结果汇报时发生错误: {str(e)}")
        return CommonResponse(
            code=1,
            msg=f"处理失败: {str(e)}"
        )



@router.post("/dmr/info/result", response_model=CommonResponse)
async def report_dmr_result(request: DMRResultPayload):
    """
    硬件信息结果汇报接口
    
    此接口等待EK调用，调用后将整理好的信息上报给服务端
    """
    try:

        # 记录详细的EK结果信息
        logger.info(f"dmr结果详情: {request}")

        # 是否成功
        if request.event.status_code == "0":
            # 清除硬件信息获取定时任务
            task_id = cache.get(HARDWARE_INFO_TASK_ID)
            if task_id:
                clear_timeout(task_id)

        body = {
            "name": request.tool,
            "type": request.event.status_code,
            "dmr_config": request.event.details.output_data,
        }

        set_dmr_info(body)

        # 如果测试中则不上报，调用逻辑在测试结束上报
        agent_status = get_agent_status_by_key('test')
        logger.info(f"测试状态: {agent_status}{type(agent_status)}")
        if not agent_status:
            # 上报硬件信息
            logger.info("开始调用：upload_dmr")
            upload_dmr()


        return CommonResponse(
            code=0,
            msg="success"
        )
        
        
    except Exception as e:
        logger.error(f"处理结果汇报时发生错误: {str(e)}")
        return CommonResponse(
            code=1,
            msg=f"处理失败: {str(e)}"
        )


def upload_dmr():
    """上报 dmr 硬件信息"""
    logger.info("调用了：upload_dmr")
    info = get_dmr_info()
    logger.info(f"dmr 硬件信息上报: {info}")
    if info:
        
        # 清除硬件信息上报定时任务, 避免重复上报
        task_id = get_dmr_upload_task_id()
        if task_id:
            clear_timeout(task_id)
            set_dmr_upload_task_id("")

        # 硬件信息上报
        res = http_post(url="/host/agent/hardware/report", data = info)
        
        logger.info(f"硬件信息上报结果: {res}")

        res_data = res.get('data', {})
        res_code = res_data.get('code', 0)
        if res_code != 200:
            logger.error(f"硬件信息上报失败: {res}")

            # 定时 15分钟后再次上报
            tack_id = set_timeout(900, upload_dmr)
            set_dmr_upload_task_id(tack_id)

            # 停止websocket服务
            from ..utils.websocket_sync_utils import stop_websocket_sync
            stop_websocket_sync()
            
            return False
        
        set_agent_status(sut=False)
        set_dmr_info(None)
        
        # 启动WebSocket服务
        from ..utils.websocket_sync_utils import start_websocket_sync
        start_websocket_sync(True)

        logger.info("硬件信息上报成功")
        # 执行更新补偿
        update_app()

    return True
