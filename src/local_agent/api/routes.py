#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API路由定义
定义所有FastAPI接口路由
"""

from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Any

from ..config import get_config
from ..logger import get_logger
from local_agent.utils.http_client import http_post
from ..utils.timer_utils import clear_timeout
from ..core.global_cache import cache
from ..core.constants import HARDWARE_INFO_TASK_ID

router = APIRouter()
logger = get_logger(__name__)
config = get_config()


class EKResultRequest(BaseModel):
    """EK结果汇报请求模型"""
    tool: str
    timestamp: str
    session_id: str
    event: Dict[str, Any]


class CommonResponse(BaseModel):
    """通用响应模型"""
    code: int  # 0-成功, 1-失败
    msg: str


@router.post("/ek/start/result", response_model=CommonResponse)
async def ek_start_result(request: EKResultRequest):
    """
    EK启动结果汇报接口
    
    
    """
    logger.info(f"启动结果: {request}")
    
    return CommonResponse(
        code=0,
        msg='success'
    )


@router.post("/ek/test/result", response_model=CommonResponse)
async def report_tool_result(request: EKResultRequest):
    """
    EK结果汇报接口
    
    此接口等待EK调用，调用后将整理好的信息上报给服务端
    """
    try:
        
        logger.info(f"ek 结果详情: {request}")

        # 记录详细的EK结果信息
        ek_result_info = {
            "tool_name": request.tool,
            "tc_id": request.event.details.tc_id,
            "session_id": request.session_id,
            "status": request.event.details.status_code,
            "timestamp": datetime.now().isoformat()
        }

        # 测试结果上报
        res = http_post(rul="/host/agent/testcase/report", data={
            "tc_id": request.tc_id,
            "status": request.status,
            "result_msg": request.result,
            "log_url": request.log_path,
        })
        
        res_data = res.get('data', {})
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
async def report_tool_result(request: EKResultRequest):
    """
    EK结果汇报接口
    
    此接口等待EK调用，调用后将整理好的信息上报给服务端
    """
    try:

        # 记录详细的EK结果信息
        ek_result_info = {
            "tool_name": request.tool,
            "tc_id": request.event.details.tc_id,
            "session_id": request.session_id,
            "status": request.event.details.status_code,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"dmr结果详情: {request}")

        # 硬件信息上报
        res = http_post(url="/host/agent/hardware/report", data={
            "name": "Updated Agent Config",
            "dmr_config": request.result,
        })
        
        res_data = res.get('data', {})

        # 清除硬件信息获取定时任务
        task_id = cache.get(HARDWARE_INFO_TASK_ID)
        if task_id:
            clear_timeout(task_id)

        # 启动WebSocket服务
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            manager = await get_websocket_manager()
            if await manager.start():
                logger.info("WebSocket服务启动成功")
            else:
                logger.warning("WebSocket服务启动失败")
        except Exception as e:
            logger.error(f"启动WebSocket服务时出错: {e}")

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


