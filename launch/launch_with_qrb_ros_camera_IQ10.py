# Copyright (c) Qualcomm Technologies, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause-Clear

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.descriptions import ComposableNode
from launch_ros.actions import ComposableNodeContainer, Node
from launch.logging import get_logger
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    default_label_file = "/opt/coco8.yaml"
    default_model_path = "/opt/model/yolov8_seg.bin"
    default_nms_iou_thres = "0.5"
    default_nms_score_thres = "0.7"
    default_target_res = "640x640"
    default_tensor_fmt = "nhwc"
    default_normalize = "True"
    default_data_type = "float32"

    camera_id_arg = DeclareLaunchArgument(
        'camera_id', default_value='5',
        description='Camera ID: inputId for QCarCam (e.g. 11/6)')

    width_arg  = DeclareLaunchArgument('width',  default_value='1280', description='Stream width in pixels')
    height_arg = DeclareLaunchArgument('height', default_value='720',  description='Stream height in pixels')
    fps_arg    = DeclareLaunchArgument('fps',    default_value='30',   description='Target frame rate')

    config_dir = get_package_share_directory('qrb_ros_camera')
    camera_info_path_arg = DeclareLaunchArgument(
        'camera_info_path',
        default_value=os.path.join(config_dir, 'config', 'camera_info_OX03F10_yuv.yaml'),
        description='Absolute path to camera intrinsic YAML file')

    dump_arg = DeclareLaunchArgument('dump', default_value='False', description='Dump frames to disk')

    target_res_arg = DeclareLaunchArgument(
        "target_res", default_value=default_target_res, description="resolution required by model")
    normalize_arg  = DeclareLaunchArgument(
        "normalize",  default_value=default_normalize,  description="whether need normalize")
    tensor_fmt_arg = DeclareLaunchArgument(
        "tensor_fmt", default_value=default_tensor_fmt, description="nhwc or nchw")
    data_type_arg  = DeclareLaunchArgument(
        "data_type",  default_value=default_data_type,  description="float32 float64 uint8")
    label_file_arg = DeclareLaunchArgument(
        "label_file", default_value=default_label_file, description="label files for yolov8 model")
    model_file_arg = DeclareLaunchArgument(
        "model",      default_value=default_model_path, description="YOLOv8 segmentation model file path")
    score_thres_arg = DeclareLaunchArgument(
        "score_thres", default_value=default_nms_score_thres, description="score threshold, 0.0~1.0")
    iou_thres_arg  = DeclareLaunchArgument(
        "iou_thres",  default_value=default_nms_iou_thres,   description="iou threshold, 0.0~1.0")

    camera_id        = LaunchConfiguration('camera_id')
    width            = LaunchConfiguration('width')
    height           = LaunchConfiguration('height')
    fps              = LaunchConfiguration('fps')
    camera_info_path = LaunchConfiguration('camera_info_path')

    image_topic = ['/cam', camera_id, '_stream1']

    camera_node = ComposableNode(
        package='qrb_ros_camera',
        namespace="",
        plugin='qrb_ros::camera::CameraNode',
        name='camera_node',
        parameters=[{
            'camera_id':        PythonExpression(["int('", camera_id, "')"]),
            'stream_size':      1,
            'stream_name':      ['stream1'],
            'stream1.height':   PythonExpression(["int('", height, "')"]),
            'stream1.width':    PythonExpression(["int('", width,  "')"]),
            'stream1.fps':      PythonExpression(["int('", fps,    "')"]),
            'camera_info_path': camera_info_path,
            'dump': False,
        }],
        remappings=[(image_topic, '/image_raw')],
    )

    ## sub: /input_image
    ## pub: /encoded_image
    ## pub: /resized_image
    preprocess_node = ComposableNode(
        package="qrb_ros_cv_tensor_common_process",
        plugin="qrb_ros::cv_tensor_common_process::CvTensorCommonProcessNode",
        name="yolo_preprocess_node",
        parameters=[
            {"target_res": LaunchConfiguration("target_res")},
            {"normalize": LaunchConfiguration("normalize")},
            {"tensor_fmt": LaunchConfiguration("tensor_fmt")},
            {"data_type": LaunchConfiguration("data_type")},
        ],
        remappings = [
            ("input_image", "/image_raw"),
            ("encoded_image", "qrb_inference_input_tensor"),
        ],
    )

    ## sub: /qrb_inference_input_tensor
    ## pub: /output_tensor (remap to /yolo_segment_tensor_output)
    inference_node = ComposableNode(
        package='qrb_ros_nn_inference',
        plugin='qrb_ros::nn_inference::QrbRosInferenceNode',
        name='nn_inference_node',
        parameters=[{
            'backend_option': "/usr/lib/libQnnHtp.so",
            #'backend_option':"",
            'model_path': LaunchConfiguration("model"),
        }],
        remappings=[
            ('qrb_inference_output_tensor', 'yolo_segment_tensor_output'),
        ]
    )


    ## sub: /yolo_segment_tensor_output
    ## pub: /yolo_segment_result
    postprocess_node = ComposableNode(
        package="qrb_ros_yolo_process",
        plugin="qrb_ros::yolo_process::YoloSegPostProcessNode",
        name="yolo_segment_postprocess_node",
        parameters=[
            {"label_file": LaunchConfiguration("label_file")},
            {"score_thres": LaunchConfiguration("score_thres")},
            {"iou_thres": LaunchConfiguration("iou_thres")},
        ],
    )

    ## sub:
    ##   - /yolo_segment_result
    ##   - /resized_image
    ## pub: /yolo_segment_overlay
    overlay_node = ComposableNode(
        package="qrb_ros_yolo_process",
        plugin="qrb_ros::yolo_process::YoloSegOverlayNode",
        name="yolo_segment_overlay_node",
        parameters=[
            {"target_res": LaunchConfiguration("target_res"),
             "mask_res": "160x160"
             },
        ],
    )

    container = ComposableNodeContainer(
        name="yolo_node_container",
        namespace="",
        package="rclcpp_components",
        executable="component_container",
        composable_node_descriptions=[camera_node,overlay_node, postprocess_node, inference_node, preprocess_node],
        output="screen",
        #arguments=['--ros-args', '--log-level', 'debug']
    )

    return LaunchDescription(
        [
            camera_id_arg,
            width_arg,
            height_arg,
            fps_arg,
            camera_info_path_arg,
            dump_arg,
            label_file_arg,
            model_file_arg,
            score_thres_arg,
            iou_thres_arg,
            target_res_arg,
            normalize_arg,
            tensor_fmt_arg,
            data_type_arg,
            container,
            LogInfo(msg=image_topic),
        ]
    )


