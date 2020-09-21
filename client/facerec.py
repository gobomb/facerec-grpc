import face_recognition
import numpy as np
from io import BytesIO
import traceback
import grpc
import threading
import os
from concurrent import futures
from multiprocessing import Process, Manager, cpu_count, set_start_method
import sys

sys.path.append("rpc")
import face_pb2
import face_pb2_grpc

# Load a sample picture and learn how to recognize it.
bing_image = face_recognition.load_image_file("known_people/binght.jpg")
bing_face_encoding = face_recognition.face_encodings(bing_image)[0]

# Load a second sample picture and learn how to recognize it.
cym_image = face_recognition.load_image_file("known_people/cym.jpg")
cym_face_encoding = face_recognition.face_encodings(cym_image)[0]

# Create arrays of known face encodings and their names
known_face_encodings = [
    bing_face_encoding,
    cym_face_encoding
]
known_face_names = [
    "Bing",
    "Cym"
]

# Initialize some variables
_HOST = '192.168.1.109'
_PORT = '9900'
ideal_distance = 0.35


def encode_frame(pb_frame):
    # numpy to bytes
    nda_bytes = BytesIO()
    np.save(nda_bytes, pb_frame, allow_pickle=False)
    return nda_bytes


def decode_frame(ndarray):
    # bytes to numpy
    nda_bytes = BytesIO(ndarray)
    return np.load(nda_bytes, allow_pickle=False)


def find_face(rgb_small_frame):
    # Find all the faces and face encodings in the current frame of video
    face_locations = []
    face_encodings = []
    face_names = []
    face_locations = face_recognition.face_locations(rgb_small_frame)
    face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

    for face_encoding in face_encodings:
        # See if the face is a match for the known face(s)
        matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
        name = "Unknown"

        # Or instead, use the known face with the smallest distance to the new face
        face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
        if np.mean(face_distances) <= ideal_distance:
            best_match_index = np.argmin(face_distances)
            if matches[best_match_index]:
                name = known_face_names[best_match_index]
        else:
            name = "Unknown"

        face_names.append(name)
    return face_locations, face_names


def send_message(stub, worker_id):
    for response in stub.GetFrameStream(face_pb2.FrameRequest(ID=str(worker_id))):
        if response.Error:
            print("error when call rpc GetFrameStream")
            print(response.Error)
            return

        face_locations, face_names = find_face(decode_frame(response.Rgb_small_frame))
        locations = []
        for i in range(0, len(face_locations)):
            lc = []
            for j in range(0, len(face_locations[i])):
                lc.append(face_locations[i][j])
            locations.append(face_pb2.Location(Loc=lc))
        try:
            yield face_pb2.LocationsStream(
                ID=response.ID,
                Face_locations=locations,
                Face_names=face_names,
            )
        except Exception as ex:
            traceback.print_exc()


# def yieldLocations(stub, worker_id):
#     for location in send_message(stub, worker_id):
#         try:
#             yield location
#         except StopIteration as si:
#             print("StopIteration")
#             traceback.print_exc()
#         except Exception as ex:
#             traceback.print_exc()

def run():
    p = []
    worker_num = 3
    if 'WORKER_NUM' in os.environ:
        worker_num = int(os.environ['WORKER_NUM'])
    if 'PODNAME' in os.environ:
        name = os.environ['PODNAME']
    else:
        name = 'default'
    if 'NODE_HOST' in os.environ:
        global _HOST
        _HOST = os.environ['NODE_HOST']
    if 'DAEMON_PORT' in os.environ:
        global _PORT
        _PORT = os.environ['DAEMON_PORT']

    for worker_id in range(0, worker_num):
        worker_name = name + '_' + str(worker_id)
        print(worker_name + ' start')
        p.append(Process(target=client, args=(worker_name, worker_num,)))
        p[worker_id].start()


def client(worker_id, worker_num):
    with grpc.insecure_channel(_HOST + ':' + _PORT) as channel:
        stub = face_pb2_grpc.FaceServiceStub(channel)
        try:
            stub.DisplayLocations(send_message(stub, worker_id))
            print("try")
        except StopIteration as si:
            print("StopIteration")
            traceback.print_exc()
        except Exception as ex:
            traceback.print_exc()


if __name__ == '__main__':
    run()
