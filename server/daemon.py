import cv2
import numpy as np
from io import BytesIO
import traceback

import grpc
import sys
import os
from concurrent import futures
from multiprocessing import Process, Manager, cpu_count, set_start_method
import time
import numpy
import threading

import platform
sys.path.append("rpc")
import face_pb2 
import face_pb2_grpc

_HOST='0.0.0.0'
_PORT='9900'
_RPC_WORKER = 8


def encode_frame(pb_frame):
    # numpy 转 bytes
    nda_bytes = BytesIO()
    np.save(nda_bytes, pb_frame, allow_pickle=False)
    return nda_bytes
            
def decode_frame(nda_bytes):
    # bytes转numpy
    nda_bytes = BytesIO(nda_proto.ndarray)
    return np.load(nda_bytes, allow_pickle=False)
            
class FaceService(face_pb2_grpc.FaceServiceServicer):
    def GetFrameStream(self,request,context):
        worker_id, read_frame_list, write_frame_list, Global, worker_num = rpc_helper.getVal()
        Global.is_called = True
        print("\rIncomming connection which ID is: {0}".format(request.ID))
        try:
            while not Global.is_exit:
                        # Wait to read
                        while  Global.read_num != prev_id(Global.buff_num, worker_num):
                            # If the user has requested to end the app, then stop waiting for webcam frames
                            if Global.is_exit:
                                break

                            time.sleep(0.01)

                        # Delay to make the video look smoother
                        time.sleep(Global.frame_delay)

                        # Read a single frame from frame list
                        frame_process = read_frame_list[Global.read_num]

                        # # Expect next worker to read frame
                        # Global.read_num = next_id(Global.read_num, worker_num)

                        # Convert the image from BGR color (which OpenCV uses) to RGB color (which face_recognition uses)
                        rgb_frame = frame_process[:, :, ::-1]
                        
                        byteFrame = encode_frame(rgb_frame).getvalue()
                        
                        yield face_pb2.FrameStream(
                                ID = request.ID,
                                Rgb_small_frame = byteFrame ,
                                Status = face_pb2.STATUS_OK,
                        )   
                        
        except Exception as ex:
            traceback.print_exc()
            Global.is_called = False

        finally:
            Global.is_called = False
            print("\rIncomming connection closed which ID: {0}".format(request.ID))

        
    def DisplayLocations(self,request_iterator,context):
        worker_id, read_frame_list, write_frame_list, Global, worker_num = rpc_helper.getVal()
        Global.is_called = True

        try:
            for message in request_iterator:
                # get face_locations, face_names
                face_names = message.Face_names
                face_locations = []
                for i in range (0,len(message.Face_locations)):
                    face_locations.append(tuple(message.Face_locations[i].Loc))

                # Read a single frame from frame list
                frame_process = read_frame_list[Global.read_num]
                # Expect next worker to read frame
                Global.read_num = next_id(Global.read_num, worker_num)

                # Display the results

                for (top, right, bottom, left), name in zip(face_locations, face_names):
                    # Draw a box around the face
                    cv2.rectangle(frame_process, (left, top), (right, bottom), (0, 0, 255), 2)

                    # Draw a label with a name below the face
                    cv2.rectangle(frame_process, (left, bottom - 35), (right, bottom), (0, 0, 255), cv2.FILLED)
                    font = cv2.FONT_HERSHEY_DUPLEX
                    cv2.putText(frame_process, name, (left + 6, bottom - 6), font, 1.0, (255, 255, 255), 1)

                # # Wait to write
                # while Global.write_num != worker_id:
                #     time.sleep(0.01)

                # Send frame to global
                write_frame_list[Global.write_num] = frame_process

                # Expect next worker to write frame
                Global.write_num = next_id(Global.write_num, worker_num)

            return face_pb2.LocationResponse(
                Status = face_pb2.STATUS_OK,
            )
        except grpc.RpcError as rpc_error_call:
            code = rpc_error_call.code()
            print(code, file=sys.stderr)
            details = rpc_error_call.details()
            print("err='RPCError DisplayLocations'")
            print("errMore=\"" + details + "\"")
        except Exception as ex:
            traceback.print_exc()
            Global.is_called = False
        finally:
            Global.is_called = False
            print("\rDisplay face cube stop -- ID: {0}".format(request.ID))

        


class helper():
    def setVal(self,worker_id, read_frame_list, write_frame_list, Global, worker_num):
        helper.worker_id = worker_id
        helper.read_frame_list = read_frame_list
        helper.write_frame_list = write_frame_list
        helper.Global = Global
        helper.worker_num = worker_num
    def getVal(self):
        return helper.worker_id,helper.read_frame_list ,helper.write_frame_list,helper.Global ,helper.worker_num 

rpc_helper = helper()

def serve(worker_id, read_frame_list, write_frame_list, Global, worker_num):
    print("start serving rpc")

    rpc_helper.setVal(worker_id, read_frame_list, write_frame_list, Global, worker_num)
    grpcServer = grpc.server(futures.ThreadPoolExecutor(max_workers=_RPC_WORKER))
    face_pb2_grpc.add_FaceServiceServicer_to_server(FaceService(), grpcServer)

    grpcServer.add_insecure_port("{0}:{1}".format(_HOST, _PORT))
    grpcServer.start()
    print("waiting for incomming connection at {0}:{1}".format(_HOST, _PORT))
    grpcServer.wait_for_termination()


def frame_helper(worker_id, read_frame_list, write_frame_list, Global, worker_num):
    print("frame_helper {0}/{1} start".format(worker_id,worker_num))
    while not Global.is_exit:
        # Wait to read
        while Global.is_called or  Global.read_num != worker_id or Global.read_num != prev_id(Global.buff_num, worker_num):

            # If the user has requested to end the app, then stop waiting for webcam frames
            if Global.is_exit:
                break

            time.sleep(0.01)

        # Delay to make the video look smoother
        time.sleep(Global.frame_delay)

        # Read a single frame from frame list
        frame_process = read_frame_list[worker_id]

        # Expect next worker to read frame
        Global.read_num = next_id(Global.read_num, worker_num)
        
        # Wait to write
        while Global.write_num != worker_id:
            time.sleep(0.01)

        # Send frame to global
        write_frame_list[worker_id] = frame_process

        # Expect next worker to write frame
        Global.write_num = next_id(Global.write_num, worker_num)
        



def frame_process(worker_id, read_frame_list, write_frame_list, Global, worker_num):
    print("frame_process start")
    while not Global.is_exit:
        # Wait to read

        while Global.read_num != worker_id  or Global.read_num != prev_id(Global.buff_num, worker_num):
            # If the user has requested to end the app, then stop waiting for webcam frames
            if Global.is_exit:
                break

            # If there isn't any rpc service called, just refract the frame
            if not Global.is_called and Global.read_num == Global.rpc_id and  Global.read_num == prev_id(Global.buff_num, worker_num):
                frame_process = read_frame_list[Global.read_num]
                
                # Delay to make the video look smoother

                time.sleep(Global.frame_delay)
                Global.read_num = next_id(Global.read_num, worker_num)
                       
                 # Wait to write

                while Global.write_num != Global.rpc_id :
                    if not Global.is_called:
                        break
                    time.sleep(0.01)

                # Send frame to global

                write_frame_list[Global.rpc_id] = frame_process

                # Expect next worker to write frame
                Global.write_num = next_id(Global.write_num, worker_num)

            time.sleep(0.01)
        
        # Delay to make the video look smoother
        time.sleep(Global.frame_delay)


        # Read a single frame from frame list
        frame_process = read_frame_list[worker_id]

        # Expect next worker to read frame
        Global.read_num = next_id(Global.read_num, worker_num)

        # Wait to write

        while Global.write_num != worker_id :
            if not Global.is_called:
                break

            time.sleep(0.01)

        # Send frame to global

        write_frame_list[worker_id] = frame_process

        # Expect next worker to write frame
        Global.write_num = next_id(Global.write_num, worker_num)



# Get next worker's id
def next_id(current_id, worker_num):
    if current_id == worker_num:
        return 1
    else:
        return current_id + 1


# Get previous worker's id
def prev_id(current_id, worker_num):
    if current_id == 1:
        return worker_num
    else:
        return current_id - 1


# A subprocess use to capture frames.
def capture(read_frame_list, Global, worker_num):
    # Get a reference to webcam #0 (the default one)
    video_capture = cv2.VideoCapture(0)
    print("capture start")

    # video_capture.set(3, 640)  # Width of the frames in the video stream.
    # video_capture.set(4, 480)  # Height of the frames in the video stream.
    # video_capture.set(5, 40) # Frame rate.
    print("Width: %d, Height: %d, FPS: %d" % (video_capture.get(3), video_capture.get(4), video_capture.get(5)))

    while not Global.is_exit:
        # If it's time to read a frame
        if Global.buff_num != next_id(Global.read_num, worker_num):
            # Grab a single frame of video
            ret, frame = video_capture.read()
            read_frame_list[Global.buff_num] = frame
            Global.buff_num = next_id(Global.buff_num, worker_num)
        else:
            time.sleep(0.01)

    # Release webcam
    video_capture.release()


def run():

    # Fix Bug on MacOS
    if platform.system() == 'Darwin':
        set_start_method('forkserver')

    # Global variables
    Global = Manager().Namespace()
    Global.buff_num = 1
    Global.read_num = 1
    Global.write_num = 1
    Global.frame_delay = 0
    Global.is_exit = False
    Global.is_called = False
    read_frame_list = Manager().dict()
    write_frame_list = Manager().dict()

    if 'WORKER_NUM' in os.environ:
        worker_num = os.environ['WORKER_NUM']
    else:
        name = 'default'

    # Number of workers (subprocess use to process frames)
    if cpu_count() > 2:
        worker_num = cpu_count() - 2  # 1 for capturing frames, 1 for rpc server
    else:
        worker_num = 2

    worker_num = 2

    Global.rpc_id = worker_num + 1

    # Subprocess list
    p = []

    # Create a thread to capture frames (if uses subprocess, it will crash on Mac)
    p.append(threading.Thread(target=capture, args=(read_frame_list, Global, worker_num,)))
    p[0].start()




    # Create workers
    for worker_id in range(1, worker_num + 1):
        p.append(Process(target=frame_helper, args=(worker_id, read_frame_list, write_frame_list, Global, worker_num,)))
        p[worker_id].start()

    p.append(Process(target=serve, args=(8, read_frame_list, write_frame_list, Global, worker_num,)))
    p[worker_num+1].start()


    # Start to show video
    last_num = 1
    fps_list = []
    tmp_time = time.time()
    while not Global.is_exit:

        while Global.write_num != last_num:
            last_num = int(Global.write_num)

            # Calculate fps
            delay = time.time() - tmp_time
            tmp_time = time.time()
            fps_list.append(delay)
            if len(fps_list) > 5 * worker_num:
                fps_list.pop(0)
            fps = len(fps_list) / numpy.sum(fps_list)

            sys.stdout.write("\r fps: %.2f" %fps)
            sys.stdout.flush()



            # Calculate frame delay, in order to make the video look smoother.
            # When fps is higher, should use a smaller ratio, or fps will be limited in a lower value.
            # Larger ratio can make the video look smoother, but fps will hard to become higher.
            # Smaller ratio can make fps higher, but the video looks not too smoother.
            # The ratios below are tested many times.
            if fps < 6:
                Global.frame_delay = (1 / fps) * 0.75
            elif fps < 20:
                Global.frame_delay = (1 / fps) * 0.5
            elif fps < 30:
                Global.frame_delay = (1 / fps) * 0.25
            else:
                Global.frame_delay = 0

            # Display the resulting image
            cv2.imshow('Video', write_frame_list[prev_id(Global.write_num, worker_num)])

        # Hit 'q' on the keyboard to quit!
        if cv2.waitKey(1) & 0xFF == ord('q'):
            Global.is_exit = True
            break

        time.sleep(0.01)

    # Quit
    cv2.destroyAllWindows()


if __name__ == '__main__':
    run()
