

class EncodingProfile:

    def __init__(self,name,bitrate,codec,target_height,returnURL):
        self.name = name
        self.bitrate = bitrate
        self.codec = codec
        self.target_height=target_height
        self.returnURL=returnURL

    def __init__(self,D):
        self.name = D["name"]
        self.bitrate = D["bitrate"]
        self.codec = D["codec"]
        self.target_height=D["height"]
        self.returnURL=D["returnURL"]
       # self.target_width  = math.trunc(float(target_height / context["track_height"] * context["track_width"] / 2) * 2