

// import $ from "jquery";

$("#btn_record").on("click", function() {
    // start recording
  $.ajax({
    url: '../start',
    type: 'POST',
    data: {
      'start': 'start'
    },
    success: function (data) {
    }
  })
});

$('#btn_stop').on( "click", function () {
  //stop recording
  swal({
    title: "Are you sure?",
    text: "This will stop recording immediately.",
    type: "warning",
    showCancelButton: true,
    confirmButtonClass: "btn-danger",
    confirmButtonText: "Yes, stop it!",
    closeOnConfirm: true
  },
  function(){
    $.ajax({
      url: '../stop',
      type: 'POST', data: {
        'stop': 'stop'
      },
      success: function (data) {
      }
    });
  });
});

(function worker() {
  $.ajax({
    url: '../status',
    dataType: 'json',
    success: function(data) {
      // $('.result').html(data);
      $('#error_connection_failed').hide();
      $('#time').text(data['time_string']);
      if (data['status'] === 'IDLE') {
        $('#btn_record').removeAttr('disabled');
        $('#btn_stop').attr('disabled', 'disabled');
        $('#status_stopped').show();
        $('#filename').text("*.mp3");
      } else {
        $('#status_stopped').hide();
      }
      if (data['status'] === 'RECORDING') {
        $('#btn_stop').removeAttr('disabled');
        $('#btn_record').attr('disabled', 'disabled');
        $('#status_recording').show();
        $('#filename').text(data['filename']);
      } else {
        $('#status_recording').hide();
      }
      if (data['status'] === 'ERROR' || data['status'] === 'WRITING' ) {
        $('#btn_stop').attr('disabled', 'disabled');
        $('#btn_record').attr('disabled', 'disabled');
        if (data['status'] === 'ERROR' ) {
          $('#error_unknown').show();
          $('#warning_busy').hide();
        } else {
          $('#error_unknown').hide();
          $('#warning_busy').show();
        }
      } else {
        $('#error_unknown').hide();
        $('#warning_busy').hide();
      }
    },
    error: function (request, text_status, error_thrown) {
      $('#error_unknown').show();
      $('#error_message').text(text_status);
      $('#btn_stop').attr('disabled', 'disabled');
      $('#btn_record').attr('disabled', 'disabled');
    },
    complete: function() {
      // Schedule the next request when the current one's complete
      setTimeout(worker, 1000);
    }
  });
})();