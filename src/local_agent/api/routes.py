#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API route definitions
Define all FastAPI interface routes
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
    """EK result reporting request model"""
    type: str
    status_code: str
    details: Dict[str, Any]

class EKResultRequest(BaseModel):
    """EK result reporting request model"""
    tool: str
    timestamp: str
    session_id: str
    event: EKResultEvent

class DMRResultDetails(BaseModel):
    """EK result reporting request model"""
    mode: str
    output_file: str
    output_data: Dict[str, Any]

class DMRResultEvent(BaseModel):
    """EK result reporting request model"""
    type: str
    status_code: str
    details: DMRResultDetails

class DMRResultPayload(BaseModel):
    """EK result reporting request model"""
    tool: str
    timestamp: str
    event: DMRResultEvent

class DMRResultRequest(BaseModel):
    """EK result reporting request model"""
    Payload: DMRResultPayload

class CommonResponse(BaseModel):
    """Common response model"""
    code: int  # 0-Success, 1-Failure
    msg: str


@router.post("/ek/start/result", response_model=CommonResponse)
async def ek_start_result(request: EKResultRequest):
    """
    EK start result reporting interface
    
    
    """
    try:
        
        logger.info(f"Start result: {request}")

        event = request.event

        details = event.details

        # Start result reporting
        case_res = http_post(url="/host/agent/testcase/report", data={
            "tc_id": details.get('tc_id', ''),
            # "state": 1,
            "state": 1 if event.status_code == '0' else 3,
            "result_msg": "{\"code\":\"200\",\"msg\":\"ok\"}",
            "log_url": "None",
        })

        if event.status_code == '1':
            return CommonResponse(
                code=0,
                msg="success"
            )

        # due_time = TimeUtils.add_minutes_to_current(details.get('estimated_duration', 0))

        # Report test case expected end time
        res = http_put(url="/host/agent/testcase/due-time", data={
            "tc_id": details.get('tc_id', ''),
            "due_time": int(details.get('estimated_duration', 0))
        })

        logger.debug(f"Start result report response: {res}")
        
        res_data = res.get('data', {})
        res_code = res_data.get('code', 0)
        if res_code != 200:
            logger.error(f"Start result report failed: {res}")

        set_agent_status(test=True)
        return CommonResponse(
            code=res_data.get('code'),
            msg=res_data.get('message')
        )

    except Exception as e:
        logger.error(f"Error occurred while processing start result report: {str(e)}")
        return CommonResponse(
            code=1,
            msg=f"Processing failed: {str(e)}"
        )


@router.post("/ek/test/result", response_model=CommonResponse)
async def report_tool_result(request: EKResultRequest):
    """
    EK result reporting interface
    
    This interface waits for EK calls, and after being called, it reports the organized information to the server
    """
    try:
        
        logger.info(f"EK result details: {request}")

        event = request.event

        details = event.details

        # Test result reporting
        res = http_post(url="/host/agent/testcase/report", data={
            "tc_id": details.get('tc_id', ''),
            "state": 2 if event.status_code == '0' else 3,
            "result_msg": "{\"code\":\"200\",\"msg\":\"ok\"}",
            "log_url": "None",
        })

        logger.debug(f"Test result report response: {res}")
        
        res_data = res.get('data', {})
        res_code = res_data.get('code', 0)
        if res_code != 200:
            logger.error(f"Test result report failed: {res}")

            return CommonResponse(
                code=res_data.get('code'),
                msg=res_data.get('message')
            )
        
        # Report hardware info
        dmr_res = upload_dmr()

        if dmr_res:
            # Record test status
            set_agent_status(test=False)

        return CommonResponse(
            code=res_data.get('code'),
            msg=res_data.get('message')
        )

    except Exception as e:
        logger.error(f"Error occurred while processing result report: {str(e)}")
        return CommonResponse(
            code=1,
            msg=f"Processing failed: {str(e)}"
        )



@router.post("/dmr/info/result", response_model=CommonResponse)
async def report_dmr_result(request: DMRResultPayload):
    """
    Hardware info result reporting interface
    
    This interface waits for EK calls, and after being called, it reports the organized information to the server
    """
    try:

        # Record detailed EK result info
        logger.info(f"DMR result details: {request}")

        # Whether successful
        if request.event.status_code == "0":
            # Clear hardware info retrieval timed task
            task_id = cache.get(HARDWARE_INFO_TASK_ID)
            if task_id:
                clear_timeout(task_id)

        body = {
            "name": request.tool,
            "type": request.event.status_code,
            "dmr_config": request.event.details.output_data,
        }

        set_dmr_info(body)

        # If in test then do not report, call logic is in test end reporting
        agent_status = get_agent_status_by_key('test')
        logger.info(f"Test status: {agent_status}{type(agent_status)}")
        if not agent_status:
            # Report hardware info
            logger.info("Starting call: upload_dmr")
            upload_dmr()


        return CommonResponse(
            code=0,
            msg="success"
        )
        
        
    except Exception as e:
        logger.error(f"Error occurred while processing result report: {str(e)}")
        return CommonResponse(
            code=1,
            msg=f"Processing failed: {str(e)}"
        )


def upload_dmr():
    """Report DMR hardware info"""
    logger.info("Called: upload_dmr")
    info = get_dmr_info()
    logger.info(f"DMR hardware info report: {info}")
    if info:
        
        # Clear hardware info reporting timed task to avoid duplicate reporting
        task_id = get_dmr_upload_task_id()
        if task_id:
            clear_timeout(task_id)
            set_dmr_upload_task_id("")

        # Hardware info reporting
        res = http_post(url="/host/agent/hardware/report", data = info)
        
        logger.info(f"Hardware info report result: {res}")
        
        res_data = res.get('data', {})
        res_code = res_data.get('code', 0)
        if res_code != 200:
            logger.error(f"Hardware info report failed: {res}")

            # Timed report again after 15 minutes
            tack_id = set_timeout(900, upload_dmr)
            set_dmr_upload_task_id(tack_id)

            # Stop WebSocket service
            from ..utils.websocket_sync_utils import stop_websocket_sync
            stop_websocket_sync()
            
            return False
        
        set_agent_status(sut=False)
        set_dmr_info(None)
        
        # Start WebSocket service
        from ..utils.websocket_sync_utils import start_websocket_sync
        start_websocket_sync(True)

        logger.info("Hardware info report successful")
        # Execute update compensation
        update_app()

    return True
