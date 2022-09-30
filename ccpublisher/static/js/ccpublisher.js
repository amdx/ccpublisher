// ccpublisher - Cameo Collaborator's publishing service
// Copyright (C) 2022  Archimedes Exhibitions GmbH
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as
// published by the Free Software Foundation, either version 3 of the
// License, or (at your option) any later version.

// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.

// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.


var previous_state = null;

function update_publish_buttons(running_profile_id, enqueued_resource_ids) {
    $('#profiles button.publish').each(
        function() {
            let profile_id = $(this).attr('id').replace('button-', '');
            if (running_profile_id && running_profile_id === profile_id) {
                $(this).find('.spinner').show();
                $(this).find('.button-text').text('Publishing..');
                $(this).prop('disabled', true);
            } else if (enqueued_resource_ids.has(profile_id)) {
                $(this).find('.spinner').hide();
                $(this).find('.button-text').text('Enqueued');
                $(this).prop('disabled', true);
            } else {
                $(this).find('.spinner').hide();
                $(this).find('.button-text').text('Publish');
                $(this).prop('disabled', false);
            }
        }
    )
}

function get_status() {
    $.getJSON('/api/v1/status')
        .done(function(data) {
            let enqueued_resource_ids = new Set();
            let queue_table_contents = '';

            // TODO: it might miss some transitions
            if (previous_state === 'RUNNING' && data.publisher.state === 'IDLE') {
                previous_state = null;
                $('#profiles').hide();
                $('#refresh').show();
                location.reload();
            } else {
                previous_state = data.publisher.state;
            }

            for (let idx in data.publisher.queue) {
                entry = data.publisher.queue[idx];
                enqueued_resource_ids.add(entry.task.profile.id);
                queue_table_contents += `<tr><td>${parseInt(idx)+1}</td><td>${entry.task.profile.md.category_path}/${entry.task.profile.md.name}</td></tr>`;
            }
            update_publish_buttons(
                data.publisher.current_task && data.publisher.current_task.profile.id,
                enqueued_resource_ids
            );
            $('#queue_tbody').html(queue_table_contents);

            if (data.publisher.state === 'RUNNING' || data.publisher.state === 'REFRESHING') {
                $('#spinner').show();
                $('#terminate').prop('disabled', false);
            } else {
                $('#spinner').hide();
                $('#terminate').prop('disabled', true);
            }

            $('#state').html(data.publisher.state);
            $('#qsize').html(data.publisher.queue.length);
            if (data.publisher.current_task && data.publisher.current_task.profile) {
                $('#current_project').html(
                    `${data.publisher.current_task.profile.md.category_path}/${data.publisher.current_task.profile.md.name} (running since ${Math.floor(data.publisher.current_task.elapsed)}s)`
                );
            } else {
                $('#current_project').html('No task running');
            }

            if (data.publisher.last_task) {
                $('#last_task').html(
                    `${data.publisher.last_task.profile.md.category_path}/${data.publisher.last_task.profile.md.name} (rc=${data.publisher.last_task.returncode})`
                );
            } else {
                $('#last_task').html('N/A');
            }

            if (data.publisher.queue.length > 0) {
                $('#killtasks').prop('disabled', false);
            } else {
                $('#killtasks').prop('disabled', true);
            }

            let loglines_content = data.loglines.join('\n');
            if ($('#loglines').html() != loglines_content) {
                $('#loglines').html(loglines_content);
                $('#loglines').prop('scrollTop', $('#loglines').prop('scrollHeight'));
            }
            $('#connection-error').hide();
        })
        .fail(function() {
            $('#connection-error').show();
        });
}

function publish(profile_id) {
    $.ajax(
        {
            url: '/api/v1/tasks',
            method: 'POST',
            data: {profile_id: profile_id},
            statusCode: {
                201: function() {
                    $('#toast-msg').html('Task successfully enqueued');
                    $('.toast').toast('show');
                },
                404: function() {
                    $('#toast-msg').html(`Unable to find profile ${profile_id}`);
                    $('.toast').toast('show');
                },
                500: function(xhr, status, exception) {
                    var payload = jQuery.parseJSON(xhr.responseText);
                    $('#toast-msg').html(`Unable to enqueue further tasks: ${payload.body}`);
                    $('.toast').toast('show');
                }
            },
         })
        .fail(function() {
            $('#toast-msg').html('Error while attempting to enqueue publish job');
            $('.toast').toast('show');
        });

    // Force immediate status refresh
    get_status();
}

function terminate_session()
{
    $.ajax(
        {
            url: '/api/v1/current_task',
            method: 'DELETE',
            statusCode: {
                204: function() {
                    $('#toast-msg').html('Current publishing session terminated')
                    $('.toast').toast('show');
                },
                404: function() {
                    $('#toast-msg').html('No currently running session')
                    $('.toast').toast('show');
                }
            }
         })
        .fail(function() {
            $('#toast-msg').html('Error while attempting to terminate current session')
            $('.toast').toast('show');
        });

    // Force immediate status refresh
    get_status();
}

function kill_tasks()
{
    $.ajax(
        {
            url: '/api/v1/tasks',
            method: 'DELETE',
            statusCode: {
                204: function() {
                    $('#toast-msg').html('All enqueued tasks killed')
                    $('.toast').toast('show');
                },
                404: function() {
                    $('#toast-msg').html('No currently running session')
                    $('.toast').toast('show');
                }
            }
         })
        .fail(function() {
            $('#toast-msg').html('Error while attempting to terminate current session')
            $('.toast').toast('show');
        });

    // Force immediate status refresh
    get_status();
}

function rescan_profiles()
{
    $('#toast-msg').html('Rescanning all profiles')
    $('.toast').toast('show');

    $('#rescan').find('.spinner').show();
    $('#rescan').prop('disabled', true);

    $.ajax(
        {
            url: '/api/v1/profiles?refresh=all',
            method: 'GET',
            statusCode: {
                200: function() {
                    location.reload();
                },
                500: function(xhr, status, exception) {
                    var payload = jQuery.parseJSON(xhr.responseText);
                    $('#toast-msg').html(`Cannot rescan profiles: ${payload.body}`);
                    $('.toast').toast('show');
                }
            }
         })
        .fail(function() {
            $('#toast-msg').html('Error while attempting to rescan profiles')
            $('.toast').toast('show');
            $('#rescan').find('.spinner').hide();
            $('#rescan').prop('disabled', false);
        });
}
