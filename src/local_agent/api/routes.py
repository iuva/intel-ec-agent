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

router = APIRouter()
logger = get_logger(__name__)
config = get_config()


class EKResultRequest(BaseModel):
    """EK结果汇报请求模型"""
    tool_name: str
    tc_id: str
    session_id: str
    status: int  # 0-成功, 1-失败, 2-超时
    result: Dict[str, Any]
    log_path: str
    duration: int


class CommonResponse(BaseModel):
    """通用响应模型"""
    code: int  # 0-成功, 1-失败
    msg: str


@router.post("/tool/result", response_model=CommonResponse)
async def report_tool_result(request: EKResultRequest):
    """
    EK结果汇报接口
    
    此接口等待EK调用，调用后将整理好的信息上报给服务端
    """
    try:

        # 记录详细的EK结果信息
        ek_result_info = {
            "tool_name": request.tool_name,
            "tc_id": request.tc_id,
            "session_id": request.session_id,
            "status": request.status,
            "result": request.result,
            "log_path": request.log_path,
            "duration": request.duration,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"EK结果详情: {ek_result_info}")

        if request.tool_name == 'ek':
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
        elif request.tool_name == 'em':
            # 硬件信息上报
            res = http_post(rul="/host/agent/hardware/report", data={
                "name": "Updated Agent Config",
                "dmr_config": request.result,
            })
            
            res_data = res.get('data', {})
            return CommonResponse(
                code=res_data.get('code'),
                msg=res_data.get('message')
            )
        
        return CommonResponse(
            code=0,
            msg="EK结果汇报成功"
        )
        
    except Exception as e:
        logger.error(f"处理EK结果汇报时发生错误: {str(e)}")
        return CommonResponse(
            code=1,
            msg=f"处理失败: {str(e)}"
        )

