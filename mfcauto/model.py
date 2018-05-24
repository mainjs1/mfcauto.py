"""Model type and caches for all known models"""
# pylint: disable=logging-format-interpolation, no-else-return
from threading import RLock
from .event_emitter import EventEmitter
from .constants import FCOPT, STATE, FCVIDEO, FCLEVEL

KNOWNMODELS_LOCK = RLock()
KNOWNMODELS = dict()

class Model(EventEmitter):
    """A single MyFreeCams model and her associated state"""
    def __init__(self, uid):
        self.uid = uid
        self.nm = None
        self.tags = set()
        self._lock = RLock()
        self.knownsessions = dict()
        self.whenmap = dict()
        super().__init__()
    @staticmethod
    def get_model(uid, create=True):
        """Retrieves or creates a model"""
        if isinstance(uid, str):
            uid = int(uid)
        with KNOWNMODELS_LOCK:
            if create:
                return KNOWNMODELS.setdefault(uid, Model(uid))
            else:
                return None if uid not in KNOWNMODELS else KNOWNMODELS[uid]
    @staticmethod
    def find_models(func):
        """Returns a list of models matching the given predicate"""
        with KNOWNMODELS_LOCK:
            return [m for m in KNOWNMODELS.values() if func(m)]
    @staticmethod
    def _default_session(uid):
        return {"sid":0, "uid":uid, "vs": STATE.Offline, "rc": 0}
    @property
    def bestsessionid(self):
        """ID of this model's most correct session for state tracking"""
        with self._lock:
            sessionidtouse = 0
            foundmodelsoftware = False
            for (sessionid, sessionobj) in self.knownsessions.items():
                if sessionobj.setdefault("vs", STATE.Offline) == STATE.Offline:
                    continue
                usethis = False
                if sessionobj.setdefault("model_sw", False):
                    if foundmodelsoftware:
                        if sessionid > sessionidtouse:
                            usethis = True
                    else:
                        foundmodelsoftware = True
                        usethis = True
                elif (not foundmodelsoftware) and sessionid > sessionidtouse:
                    usethis = True
                if usethis:
                    sessionidtouse = sessionid
            return sessionidtouse
    @property
    def bestsession(self):
        """dict of session details for this model's most correct session
        for state tracking"""
        with self._lock:
            return self.knownsessions.setdefault(self.bestsessionid,
                                                 Model._default_session(self.uid))
    @property
    def in_true_private(self):
        """True if this model is in a true private, False if not"""
        with self._lock:
            return (self.bestsession["vs"] == STATE.Private
                    and "truepvt" in self.bestsession
                    and self.bestsession["truepvt"])
    def merge_tags(self, new_tags):
        """Merges tag updates into this model's state and emits change events"""
        assert isinstance(new_tags, list)
        previous_tags = self.tags.copy()
        self.tags.update(new_tags)
        self.emit("tags", self, previous_tags, self.tags)
        Model.All.emit("tags", self, previous_tags, self.tags)
        self._process_whens(new_tags)
    def merge(self, payload):
        """Merges state updates from the given payload into this model's state
        and emits events for every changed property"""
        assert self.uid != -500, "We should never merge for the fake 'All' model"
        assert (isinstance(payload, dict)
                and ("lv" not in payload or payload["lv"] == FCLEVEL.MODEL))

        with self._lock:
            previoussession = self.bestsession
            currentsessionid = 0 if not "sid" in payload else payload["sid"]
            currentsession = self.knownsessions.setdefault(currentsessionid,
                                                           Model._default_session(self.uid))

            callbackstack = []

            for key in payload:
                if key == "u" or key == "m" or key == "s":
                    for key2 in payload[key]:
                        callbackstack.append((key2, self, None if not key2 in previoussession else previoussession[key2], payload[key][key2]))
                        currentsession[key2] = payload[key][key2]
                        if key == "m" and key2 == "flags":
                            # @BUGBUG - I'm just realizing that the Node version doesn't fire
                            # callbacks for individual flag changes...
                            # @TODO need to do it here too...
                            flags = payload[key][key2]
                            currentsession["truepvt"] = bool(flags & FCOPT.TRUEPVT)
                            currentsession["guests_muted"] = bool(flags & FCOPT.GUESTMUTE)
                            currentsession["basics_muted"] = bool(flags & FCOPT.BASICMUTE)
                            currentsession["model_sw"] = bool(flags & FCOPT.MODELSW)
                            # @TODO - Build a running set of leaf keys and assert that we've
                            # never seen this leaf key before, in other words, validate that
                            # this whole dict flattening approach is not losing information
                else:
                    callbackstack.append((key, self, None if not key in previoussession else previoussession[key], payload[key]))
                    currentsession[key] = payload[key]

            if currentsession["sid"] != previoussession["sid"]:
                previouskeys = set(previoussession.keys())
                currentkeys = set(currentsession.keys())
                for key in (previouskeys - currentkeys): # pylint: disable=superfluous-parens
                    callbackstack.append((key, self, previoussession[key], None))

            if (self.bestsessionid == currentsession["sid"]
                    or (self.bestsessionid == 0 and currentsession["sid"] != 0)):
                if "nm" in self.bestsession and self.bestsession["nm"] != self.nm:
                    self.nm = self.bestsession["nm"]
                for (prop, model, before, after) in callbackstack:
                    if before != after:
                        self.emit(prop, model, before, after)
                        Model.All.emit(prop, model, before, after)
                self.emit("ANY", self, payload)
                Model.All.emit("ANY", self, payload)
                self._process_whens(payload)
            self._purgeoldsessions()
    def _purgeoldsessions(self):
        with self._lock:
            for key in set(self.knownsessions.keys()):
                if ("vs" not in self.knownsessions[key]
                        or FCVIDEO(self.knownsessions[key]["vs"]) == FCVIDEO.OFFLINE):
                    del self.knownsessions[key]
    def reset(self):
        """Removes all session data for this model and sets her offline"""
        with self._lock:
            if self.uid != -500:
                for key in set(self.knownsessions.keys()):
                    if key != self.bestsessionid and self.knownsessions[key]["vs"] != FCVIDEO.OFFLINE:
                        self.knownsessions[key]["vs"] = FCVIDEO.OFFLINE
                blank = {"sid": self.bestsessionid, "uid": self.uid, "vs": FCVIDEO.OFFLINE}
                self.merge(blank)
            else:
                # When called on the special "All" model, reset all models
                with KNOWNMODELS_LOCK:
                    for model in KNOWNMODELS.values():
                        if model.uid != -500: # Ignore the fake 'All' model
                            model.reset()
    def when(self, condition, ontrue, onfalseaftertrue):
        """Registers an onTrue method to be called whenever condition returns
        true for this model and, optionally, an onFalseAfterTrue method to be
        called when condition had been true previously but is no longer true"""
        with self._lock:
            self.whenmap[condition] = {"ontrue": ontrue, "onfalseaftertrue": onfalseaftertrue, "matchedset": set()}
            self._process_whens()
    def _process_whens(self, payload=None):
        def _processor(condition, actions):
            if condition(self):
                if self.uid not in actions["matchedset"]:
                    actions["matchedset"].add(self.uid)
                    actions["ontrue"](self, payload)
            else:
                if self.uid  in actions["matchedset"]:
                    actions["matchedset"].remove(self.uid)
                    actions["onfalseaftertrue"](self, payload)
        if self.uid != -500:
            with self._lock:
                for condition, actions in self.whenmap.items():
                    _processor(condition, actions)
            with Model.All._lock:
                for condition, actions in Model.All.whenmap.items():
                    _processor(condition, actions)
    def __repr__(self):
        with self._lock:
            return ('{{"nm": {}, "uid": {}, "tags": {}, "bestsession": {}}}'
                    .format(self.nm, self.uid, self.tags, self.bestsession))
    def __str__(self):
        return self.__repr__()

Model.All = Model.get_model(-500)
__all__ = ["Model"]
