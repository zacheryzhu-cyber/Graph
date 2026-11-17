package lab;

import java.nio.file.Path;
import org.neo4j.configuration.GraphDatabaseSettings;
import org.neo4j.configuration.connectors.BoltConnector;
import org.neo4j.configuration.helpers.SocketAddress;
import org.neo4j.dbms.api.DatabaseManagementService;
import org.neo4j.dbms.api.DatabaseManagementServiceBuilder;

/** Neo4j 5.26 Community, embedded, with a Bolt listener so Python/Cypher clients connect as to a normal server.
 *  Used because Docker has no daemon here and dist.neo4j.org is not reachable (see DECISIONS.md). */
public class Server {
    public static void main(String[] args) throws Exception {
        Path home = Path.of(args.length > 0 ? args[0] : "neo4j_data");
        int port = args.length > 1 ? Integer.parseInt(args[1]) : 7687;
        DatabaseManagementService dbms = new DatabaseManagementServiceBuilder(home)
                .setConfig(BoltConnector.enabled, true)
                .setConfig(BoltConnector.listen_address, new SocketAddress("127.0.0.1", port))
                .setConfig(GraphDatabaseSettings.auth_enabled, false)
                .build();
        Runtime.getRuntime().addShutdownHook(new Thread(dbms::shutdown));
        System.out.println("NEO4J_READY bolt://127.0.0.1:" + port);
        Thread.currentThread().join();
    }
}
