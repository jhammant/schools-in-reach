<?php
/** Remove this plugin's settings when WordPress uninstalls it. */
if ( ! defined( 'WP_UNINSTALL_PLUGIN' ) ) {
    exit;
}
delete_option( 'sir_settings' );
