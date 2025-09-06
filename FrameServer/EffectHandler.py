# region Importing Effects
from Effects.CheckerboardEffect import CheckerboardEffect
from Effects.AlphaDissolveEffect import AlphaDissolveEffect
from Effects.PixelDissolveEffect import PixelDissolveEffect
from Effects.BlindsEffect import BlindsEffect
from Effects.ScrollEffect import ScrollEffect
from Effects.WipeEffect import WipeEffect
from Effects.ZoomOutEffect import ZoomOutEffect
from Effects.ZoomInEffect import ZoomInEffect
from Effects.IrisOpenEffect import IrisOpenEffect
from Effects.IrisCloseEffect import IrisCloseEffect
from Effects.BarnDoorOpenEffect import BarnDoorOpenEffect
from Effects.BarnDoorCloseEffect import BarnDoorCloseEffect
from Effects.ShrinkEffect import ShrinkEffect
from Effects.StretchEffect import StretchEffect
from Effects.LinearEffect import LinearEffect
from Effects.LumaWipeEffect import LumaWipeEffect
from Effects.SoftWipeEffect import SoftWipeEffect
from Effects.RippleEffect import RippleEffect
from Effects.SpinZoomFadeEffect import SpinZoomFadeEffect
from Effects.CrossZoomEffect import CrossZoomEffect
from Effects.SwirlEffect import SwirlEffect
from Effects.ZoomBlurEffect import ZoomBlurEffect
from Effects.PlainEffect import PlainEffect
# endregion Importing Effects

import random as rand

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
            17: RippleEffect,
            18: SpinZoomFadeEffect,
            19: CrossZoomEffect,
            20: ZoomBlurEffect,
            # 21: SwirlEffect,
            # 22: PlainEffect
        }
        self.current_effect_idx = -1
        
    def get_effects(self):
        return self.effects

    def shuffle_effects(self, effects):
        keys = list(effects.keys())
        rand.shuffle(keys)
        return keys

    def get_random_effect(self):
        '''Returns a different effect each time.'''
        shuffled_effects = list(self.effects.keys())
        if len(shuffled_effects) == 0:
            shuffled_effects = list(self.effects.keys())
        rand.shuffle(shuffled_effects)
        self.current_effect_idx = (
            self.current_effect_idx + 1) % len(shuffled_effects)
        return shuffled_effects[self.current_effect_idx]