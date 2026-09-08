from aiogram.fsm.state import StatesGroup, State


class ClientSelectionStates(StatesGroup):
    request_other_text = State()
    comment_text = State()
    find_psychologist_name = State()

    booking_phone = State()
    booking_email = State()

class SelectionStates(StatesGroup):
    selection_waiting_phone = State()
    selection_waiting_email = State()
