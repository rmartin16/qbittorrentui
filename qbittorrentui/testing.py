import urwid
import random
import logging


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] {%(name)s:%(lineno)d} %(levelname)s - %(message)s',
                    filename='/home/user/output.txt',
                    filemode='w')


class MyText(urwid.Text):
    def selectable(self):
        return True

    def keypress(self, size, key, *args, **kwargs):
        refresh(loop, None)
        return key

ui = urwid.raw_display.Screen()

# list_widget_w = urwid.Filler(urwid.Text("ignissim sodales ut eu sem integer vitae justo eget magna fermentum iaculis eu non diam phasellus vestibulum lorem sed risus ultricies tristique nulla aliquet enim tortor at auctor urna nunc id cursus metus aliquam eleifend mi in nulla posuere sollicitudin aliquam ultrices sagittis orci a scelerisque purus semper eget duis at tellus at urna condimentum mattis pellentesque id nibh tortor id aliquet lectus proin nibh nisl condimentum id venenatis a condimentum vitae sapien pellentesque habitant morbi tristique senectus et netus et malesuada fames ac turpis egestas sed tempus urna et pharetra pharetra massa massa ultricies mi quis hendrerit dolor magna eget est lorem ipsum dolor sit amet consectetur adipiscing elit pellentesque habitant morbi tristique senectus et netus et malesuada fames ac turpis egestas integer eget aliquet nibh praesent tristique magna sit amet purus gravida quis blandit turpis cursus in hac habitasse platea dictumst quisque sagittis purus sit amet volutpat consequat mauris nunc congue nisi vitae suscipit tellus mauris a diam maecenas sed enim ut sem viverra aliquet eget sit amet tellus cras adipiscing enim eu turpis egestas pretium aenean pharetra magna ac placerat vestibulum lectus mauris ultrices eros in cursus turpis massa tincidunt dui ut ornare lectus sit amet est placerat in egestas erat imperdiet sed euismod nisi porta lorem mollis aliquam ut porttitor leo a diam sollicitudin tempor id eu nisl nunc mi ipsum faucibus vitae aliquet nec ullamcorper sit amet risus nullam eget felis eget nunc lobortis mattis aliquam faucibus purus in massa tempor nec feugiat nisl pretium fusce id velit ut tortor pretium viverra suspendisse potenti nullam ac tortor vitae purus faucibus ornare suspendisse sed nisi lacus sed viverra tellus in hac habitasse platea dictumst vestibulum rhoncus est pellentesque elit ullamcorper dignissim cras tincidunt lobortis feugiat vivamus at augue eget arcu dictum varius duis at consectetur lorem donec massa sapien faucibus et molestie ac feugiat sed lectus vestibulum mattis ullamcorper velit sed ullamcorper morbi tincidunt ornare massa eget egestas purus viverra accumsan in nisl nisi scelerisque eu ultrices vitae auctor eu augue ut lectus arcu bibendum at varius vel pharetra vel turpis nunc eget lorem dolor sed viverra ipsum nunc aliquet bibendum enim facilisis gravida neque convallis a cras semper auctor neque vitae tempus quam pellentesque nec nam aliquam sem et tortor consequat id porta nibh venenatis cras sed felis eget velit aliquet sagittis id consectetur purus ut faucibus pulvinar elementum integer enim neque volutpat ac tincidunt vitae semper quis lectus nulla at volutpat diam ut venenatis tellus in metus vulputate eu scelerisque felis imperdiet proin fermentum leo vel orci porta non pulvinar neque laoreet suspendisse interdum consectetur libero id faucibus nisl tincidunt eget nullam non nisi est sit amet facilisis magna etiam tempor orci eu lobortis elementum nibh tellus molestie nunc non blandit massa enim nec dui nunc mattis enim ut tellus elementum sagittis vitae et leo duis ut diam quam nulla porttitor massa id neque aliquam vestibulum morbi blandit cursus risus at ultrices mi tempus imperdiet nulla malesuada pellentesque elit eget gravida cum sociis natoque"))

num_list = []
for count in range(1, 50):
    num_list.append(MyText(str(random.randrange(1, 100, 1))))

list_walker_w = urwid.SimpleFocusListWalker(num_list)
list_widget_w = urwid.ListBox(list_walker_w)

frame_w = urwid.Frame(header=urwid.Text("header"),
                      body=list_widget_w,
                      footer=urwid.Text("footer"))


def list_walker_modified(*args, **kwargs):
    logger.info("args: %s   kwargs: %s" % (args, kwargs))
    logger.info(list_walker_w.focus)


urwid.connect_signal(list_walker_w, name='modified', callback=list_walker_modified)


def handle_key(key):
    if key in ('q', 'Q'):
        raise urwid.ExitMainLoop()


def refresh(loop, user_data):
    loop.set_alarm_in(2, refresh)
    focus_w = list_widget_w.focus
    focus_w.set_text((urwid.AttrSpec('dark red', '', 256), focus_w.get_text()[0]))
    logger.info(focus_w)
    # frame_w.body = urwid.ListBox(urwid.SimpleFocusListWalker(num_list))


loop = urwid.MainLoop(frame_w,
                      screen=ui,
                      handle_mouse=False,
                      unhandled_input=handle_key,
                      palette=[],
                      event_loop=None,
                      pop_ups=False,
                      )

loop.set_alarm_in(1, refresh)

loop.run()







