# region Importing Effects
# endregion Importing Effects
import random as rand

from FrameServer.Effects.AlphaDissolveEffect import AlphaDissolveEffect
from FrameServer.Effects.BarnDoorCloseEffect import BarnDoorCloseEffect
from FrameServer.Effects.BarnDoorOpenEffect import BarnDoorOpenEffect
from FrameServer.Effects.BlindsEffect import BlindsEffect
from FrameServer.Effects.CheckerboardEffect import CheckerboardEffect
from FrameServer.Effects.CrossZoomEffect import CrossZoomEffect
from FrameServer.Effects.IrisCloseEffect import IrisCloseEffect
from FrameServer.Effects.IrisOpenEffect import IrisOpenEffect
from FrameServer.Effects.LinearEffect import LinearEffect
from FrameServer.Effects.LumaWipeEffect import LumaWipeEffect
from FrameServer.Effects.PixelDissolveEffect import PixelDissolveEffect
from FrameServer.Effects.ScrollEffect import ScrollEffect
from FrameServer.Effects.ShrinkEffect import ShrinkEffect
from FrameServer.Effects.SoftWipeEffect import SoftWipeEffect
from FrameServer.Effects.StretchEffect import StretchEffect
from FrameServer.Effects.WipeEffect import WipeEffect
from FrameServer.Effects.ZoomBlurEffect import ZoomBlurEffect
from FrameServer.Effects.ZoomInEffect import ZoomInEffect
from FrameServer.Effects.ZoomOutEffect import ZoomOutEffect


class EffectHandler:
    def __init__(self):
        self.effects = {
            0: AlphaDissolveEffect,
            1: PixelDissolveEffect,
            2: CheckerboardEffect,
            3: BlindsEffect,
            4: ScrollEffect,
            5: WipeEffect,
            6: ZoomOutEffect,
            7: ZoomInEffect,
            8: IrisOpenEffect,
            9: IrisCloseEffect,
            10: BarnDoorOpenEffect,
            11: BarnDoorCloseEffect,
            12: ShrinkEffect,
            13: StretchEffect,
            14: LinearEffect,
            15: LumaWipeEffect,
            16: SoftWipeEffect,
            # 17: RippleEffect,
            # 18: SpinZoomFadeEffect,
            19: CrossZoomEffect,
            20: ZoomBlurEffect,
            # 21: SwirlEffect,
            # 22: PlainEffect
        }
        self._shuffled_effects = list(self.effects.keys())
        rand.shuffle(self._shuffled_effects)
        self._effect_idx = 0

    def get_effects(self):
        return self.effects

    def shuffle_effects(self, effects):
        keys = list(effects.keys())
        rand.shuffle(keys)
        return keys

    def get_random_effect(self):
        """Return a different effect each time; reshuffle only when the deck is exhausted."""
        if self._effect_idx >= len(self._shuffled_effects):
            rand.shuffle(self._shuffled_effects)
            self._effect_idx = 0
        effect = self._shuffled_effects[self._effect_idx]
        self._effect_idx += 1
        return effect
